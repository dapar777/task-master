"""Hlavní okno aplikace Task Master."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .cardview import CardView
from .commandpalette import CommandPalette
from .constants import (
    APP_NAME,
    DEFAULT_PRIORITY,
    ORG_NAME,
    STATUS_GROUP_INDEX,
    STATUS_GROUPS,
)
from .detailpanel import TaskDetailPanel
from .filterpanel import FilterPanel
from .savedfilters import FilterStore, SavedFilter
from .savedfiltersdialog import SavedFiltersDialog
from .shortcutdialog import ShortcutDialog
from .shortcuts import COMMAND_DEFS, ShortcutManager
from .stats import StatsDialog
from .storage import Workspace, now_iso, parse_dt, parse_indented_text, serialize_node
from .taskdialog import BlockerDialog, TaskDialog, ask_paste_position
from .undo import UndoManager
from .tasktree import TaskTreeWidget, breadcrumb, sort_flat, sort_nodes

VIEW_MODES = ("tree", "list", "cards")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 760)

        self.workspace: Workspace | None = None
        self._view_mode = self.settings.value("view_mode", "tree", type=str)
        if self._view_mode not in VIEW_MODES:
            self._view_mode = "tree"
        self._current_node = None
        # úsporné zobrazení karet (Bez rušení): úkoly mimo Probíhá+Ke zpracování
        # jsou nižší. Defaultně zapnuto.
        self._compact_cards = self.settings.value("compact_cards", True, type=bool)
        self._clip = None  # schránka úkolu: {"mode": "copy"|"cut", "data": ..., "src_id": ...}
        self.undo = UndoManager()
        self.act: dict[str, QAction] = {}

        # debounce pro ukládání stavu UI do rootu workspace
        self._state_timer = QTimer(self)
        self._state_timer.setSingleShot(True)
        self._state_timer.setInterval(800)
        self._state_timer.timeout.connect(self._save_state)

        cfg_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation))
        self.shortcuts = ShortcutManager(cfg_dir / "shortcuts.json")
        self.filter_store = FilterStore(cfg_dir / "filters.json")
        self._filter_actions: list[QAction] = []

        self._build_ui()
        self._build_actions()
        self._build_menus()
        self._restore_geometry()
        self._open_initial_workspace()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # levý panel
        self.filter_panel = FilterPanel()
        self.filter_panel.filtersChanged.connect(self._on_filter_changed)
        self.filter_panel.sortChanged.connect(self._on_sort_changed)
        self.filter_panel.savedFilterSelected.connect(self._apply_saved_filter_by_id)

        self.tree = TaskTreeWidget()
        self.tree.taskSelected.connect(self._on_task_selected)
        self.tree.linkDropped.connect(self._on_link_dropped)
        self.tree.reparentRequested.connect(self._on_reparent)
        self.tree.reorderRequested.connect(self._on_reorder)
        self.tree.statusToggled.connect(self._on_status_toggled)
        self.tree.renameRequested.connect(self._on_rename)
        self.tree.itemActivated.connect(lambda *_: self._focus_editor())
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_tree_menu)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(6, 6, 6, 6)
        left_layout.addWidget(self.filter_panel)
        left_layout.addWidget(self.tree, 1)

        # pravý panel
        self.detail = TaskDetailPanel()
        self.detail.metaChanged.connect(self._on_meta_changed)
        self.detail.statusChanged.connect(self._on_status_meta_changed)
        self.detail.navigateTo.connect(self._navigate_to)
        self.detail.addRefRequested.connect(self._add_ref_dialog)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 820])
        self.main_splitter = splitter

        # režim „Bez rušení" – karty přes celou šířku
        self.card_view = CardView()
        self.card_view.cardSelected.connect(self._on_card_selected)
        self.card_view.cardOpened.connect(self._on_card_opened)
        self.card_view.cardStatusToggled.connect(self._on_status_toggled)

        # přepínání normální / karty
        self.stack = QStackedWidget()
        self.stack.addWidget(splitter)        # index 0 = strom/seznam + detail
        self.stack.addWidget(self.card_view)  # index 1 = karty
        self.setCentralWidget(self.stack)

        self.status = self.statusBar()
        # dnešní počty (vytvořené/dokončené) vlevo, cesta k prostoru vpravo
        self.today_label = QLabel("")
        self.today_label.setToolTip("Dnes vytvořené / dokončené úkoly")
        self.status.addPermanentWidget(self.today_label)
        self.ws_label = QLabel("")
        self.status.addPermanentWidget(self.ws_label)

    # ------------------------------------------------------------------
    # Akce a zkratky
    # ------------------------------------------------------------------
    def _make(self, cid: str, callback, checkable: bool = False, target=None) -> QAction:
        """Vytvoří akci, zaregistruje zkratku a (pro fokus kontext) ji přidá k cíli."""
        act = QAction(self.shortcuts.label(cid), self)
        act.setCheckable(checkable)
        if callback is not None:
            (act.toggled if checkable else act.triggered).connect(callback)
        self.shortcuts.register(cid, act)
        if target is not None:
            target.addAction(act)  # kontext Widget* -> zkratka platí při fokusu na cíli
        self.act[cid] = act
        return act

    def _build_actions(self) -> None:
        # Úkoly
        self._make("task.new", self._new_task)
        self._make("task.new_sub", self._new_subtask)
        self._make("task.rename", self._rename_dir, target=self.tree)
        self._make("task.delete", self._delete_task, target=self.tree)
        # přesun v pořadí – aktivní ve stromu i v kartách
        mu = self._make("task.move_up", lambda: self._move_task(-1), target=self.tree)
        mu.setAutoRepeat(False)  # podržení klávesy nesmí přeskočit o víc položek
        self.card_view.addAction(mu)
        md = self._make("task.move_down", lambda: self._move_task(+1), target=self.tree)
        md.setAutoRepeat(False)
        self.card_view.addAction(md)
        # priorita +/- (ve stromu i v kartách)
        pu = self._make("task.priority_up", lambda: self._change_priority(+1), target=self.tree)
        self.card_view.addAction(pu)
        pd = self._make("task.priority_down", lambda: self._change_priority(-1), target=self.tree)
        self.card_view.addAction(pd)
        # vlaječka (kdekoli – působí na aktuální úkol)
        fl = self._make("task.flag", self._toggle_flag)
        fl.setAutoRepeat(False)
        # schránka úkolů (kontext stromu)
        self._make("task.copy", self._copy_task, target=self.tree)
        self._make("task.cut", self._cut_task, target=self.tree)
        self._make("task.paste", self._paste_task, target=self.tree)
        self._make("task.paste_text", self._paste_from_text, target=self.tree)
        # přepnout hotovo (strom i karty)
        td = self._make("task.toggle_done", self._toggle_done, target=self.tree)
        td.setAutoRepeat(False)
        self.card_view.addAction(td)
        # undo (strom i karty; editor má vlastní Ctrl+Z)
        un = self._make("edit.undo", self._undo, target=self.tree)
        un.setAutoRepeat(False)
        self.card_view.addAction(un)
        # Aplikace
        self._make("app.open_workspace", self._choose_workspace)
        self._make("app.save", self._save)
        self._make("app.refresh", self._reload)
        self._make("app.shortcuts", self._open_shortcuts)
        self._make("app.command_palette", self._open_command_palette)
        self._make("app.stats", self._open_stats)
        # Filtry
        self._make("filter.save", self._save_current_filter)
        self._make("filter.manage", self._manage_filters)
        # Zobrazení – tři vzájemně výlučné režimy + cyklení
        self.view_group = QActionGroup(self)
        self.view_group.setExclusive(True)
        self.act_view: dict[str, QAction] = {}
        for cid, mode in (("view.tree", "tree"), ("view.list", "list"), ("view.cards", "cards")):
            a = QAction(self.shortcuts.label(cid), self)
            a.setCheckable(True)
            self.shortcuts.register(cid, a)
            a.triggered.connect(lambda _checked=False, m=mode: self._set_view_mode(m))
            self.view_group.addAction(a)
            self.act[cid] = a
            self.act_view[mode] = a
        self.act_view[self._view_mode].setChecked(True)
        self._make("view.cycle", self._cycle_view)
        # úsporné karty – přepínatelná akce (zkratka + klikátko v menu)
        ac = self._make("view.compact_cards", self._toggle_compact_cards, checkable=True)
        ac.setChecked(self._compact_cards)
        # Navigace / fokus
        self._make("focus.filter", self._focus_filter)
        self._make("focus.tree", self._focus_tree)
        self._make("focus.editor", self._focus_editor)
        self._make("focus.title", self._focus_title)
        self._make("focus.links", self._focus_links)

        # Editor – akce už existují, jen jim přiřaď zkratky
        for cid, action in self.detail.editor.command_actions.items():
            self.shortcuts.register(cid, action)
            self.act[cid] = action

    def _build_menus(self) -> None:
        mb = self.menuBar()

        m_file = mb.addMenu("&Soubor")
        m_file.addAction(self.act["app.open_workspace"])
        m_file.addSeparator()
        m_file.addAction(self.act["edit.undo"])
        m_file.addAction(self.act["app.save"])
        m_file.addAction(self.act["app.refresh"])
        m_file.addSeparator()
        quit_act = QAction("Konec", self)  # bez zkratky (Ctrl+Q používá přesun v pořadí)
        quit_act.triggered.connect(self.close)
        m_file.addAction(quit_act)

        m_task = mb.addMenu("Ú&kol")
        for cid in ("task.new", "task.new_sub", "task.rename", "task.delete"):
            m_task.addAction(self.act[cid])
        m_task.addSeparator()
        for cid in ("task.copy", "task.cut", "task.paste", "task.paste_text"):
            m_task.addAction(self.act[cid])
        m_task.addSeparator()
        m_task.addAction(self.act["task.move_up"])
        m_task.addAction(self.act["task.move_down"])
        m_task.addAction(self.act["task.priority_up"])
        m_task.addAction(self.act["task.priority_down"])
        m_task.addAction(self.act["task.flag"])
        m_task.addAction(self.act["task.toggle_done"])

        m_view = mb.addMenu("&Zobrazení")
        for cid in ("view.tree", "view.list", "view.cards"):
            m_view.addAction(self.act[cid])
        m_view.addAction(self.act["view.cycle"])
        m_view.addAction(self.act["view.compact_cards"])
        m_view.addSeparator()
        for cid in ("focus.filter", "focus.tree", "focus.editor", "focus.title", "focus.links"):
            m_view.addAction(self.act[cid])

        self.m_filters = mb.addMenu("&Filtry")
        self._rebuild_filter_menu()

        m_editor = mb.addMenu("&Editor")
        for cid in (
            "fmt.bold", "fmt.italic", "fmt.strike", "fmt.code", None,
            "fmt.h1", "fmt.h2", "fmt.h3", "fmt.paragraph", None,
            "fmt.bullet", "fmt.numbered", "fmt.quote", "fmt.hr", None,
            "fmt.link", "view.toggle_source",
        ):
            if cid is None:
                m_editor.addSeparator()
            else:
                m_editor.addAction(self.act[cid])

        m_settings = mb.addMenu("&Nastavení")
        m_settings.addAction(self.act["app.stats"])
        m_settings.addSeparator()
        m_settings.addAction(self.act["app.command_palette"])
        m_settings.addAction(self.act["app.shortcuts"])

    # ------------------------------------------------------------------
    # Fokus / navigace klávesnicí
    # ------------------------------------------------------------------
    def _focus_filter(self) -> None:
        self.filter_panel.name_edit.setFocus()
        self.filter_panel.name_edit.selectAll()

    def _focus_tree(self) -> None:
        self.tree.setFocus()
        if self.tree.current_node() is None and self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _focus_editor(self) -> None:
        if self.detail.isEnabled():
            self.detail.editor.edit.setFocus()

    def _focus_title(self) -> None:
        # název se needituje v metadatech – Ctrl+3 spustí inline přejmenování
        self._rename_dir()

    def _focus_links(self) -> None:
        if self.detail.isEnabled():
            self.detail.link_list.setFocus()
            if self.detail.link_list.count() and self.detail.link_list.currentRow() < 0:
                self.detail.link_list.setCurrentRow(0)

    def _open_shortcuts(self) -> None:
        ShortcutDialog(self.shortcuts, self).exec()

    def _open_command_palette(self) -> None:
        entries = []
        for cid, act in self.act.items():
            if cid == "app.command_palette":
                continue
            entries.append({
                "label": self.shortcuts.label(cid) if cid in COMMAND_DEFS else act.text(),
                "category": self.shortcuts.category(cid) if cid in COMMAND_DEFS else "",
                "shortcut": act.shortcut().toString(),
                "run": act.trigger,
            })
        for f in self.filter_store.filters:
            entries.append({
                "label": f.name,
                "category": "Filtr",
                "shortcut": f.shortcut,
                "run": (lambda fid=f.id: self._apply_saved_filter_by_id(fid)),
            })
        entries.sort(key=lambda e: (e["category"].lower(), e["label"].lower()))
        CommandPalette(entries, self).exec()

    def _open_stats(self) -> None:
        if not self.workspace:
            return
        StatsDialog(list(self.workspace.all_nodes()), self).exec()

    def _update_today_counts(self) -> None:
        """Do spodní lišty vypíše počet dnes vytvořených a dnes dokončených úkolů."""
        if not self.workspace:
            self.today_label.setText("")
            return
        today = date.today()

        def is_today(value) -> bool:
            dt = parse_dt(value)
            return dt is not None and dt.date() == today

        created = completed = 0
        for n in self.workspace.all_nodes():
            if is_today(n.meta.get("_created")):
                created += 1
            if is_today(n.meta.get("_completed")):
                completed += 1
        self.today_label.setText(f"Dnes: +{created} / ✓{completed}")

    # ------------------------------------------------------------------
    # Workspace
    # ------------------------------------------------------------------
    def _default_workspace(self) -> Path:
        return Path(__file__).resolve().parent.parent / "workspace"

    def _open_initial_workspace(self) -> None:
        saved = self.settings.value("workspace", "", type=str)
        path = Path(saved) if saved else self._default_workspace()
        self._set_workspace(path, create_samples=not saved)

    def _choose_workspace(self) -> None:
        start = str(self.workspace.root) if self.workspace else str(self._default_workspace())
        chosen = QFileDialog.getExistingDirectory(self, "Vyber pracovní prostor", start)
        if chosen:
            self._set_workspace(Path(chosen))

    def _set_workspace(self, path: Path, create_samples: bool = False) -> None:
        self.detail.discard()
        self.detail.load(None)
        self._current_node = None
        self.workspace = Workspace(path)
        self.detail.resolver = self.workspace.node_by_id
        self.card_view.resolver = self.workspace.node_by_id
        self.tree.resolver = self.workspace.node_by_id
        roots = self.workspace.load()
        if not roots and create_samples:
            self._create_samples()
            self.workspace.load()
        self.settings.setValue("workspace", str(path))
        self.ws_label.setText(f"Prostor: {path}")
        self._restore_state()

    def _restore_state(self) -> None:
        """Obnoví stav uložený v rootu workspace: filtr, zobrazení, aktivní úkol."""
        state = self.workspace.load_state() if self.workspace else {}
        f = state.get("_filter") or {}
        if f:
            self.filter_panel.apply_preset(f)
        view = state.get("_view")
        if view in VIEW_MODES:
            self._view_mode = view
            self.act_view[view].setChecked(True)
        self._populate()
        aid = state.get("_active")
        node = self.workspace.node_by_id(aid) if aid else None
        if node is not None:
            self._current_node = node
            self.detail.load(node)
            self._select_in_view(node)
        elif self._view_mode == "cards":
            self.card_view.ensure_selection()

    def _save_state(self) -> None:
        if not self.workspace:
            return
        # zachovej klíče, které si spravuje někdo jiný (např. _recent_blockers)
        state = self.workspace.load_state()
        state.update({
            "_active": self._current_node.meta.get("_id") if self._current_node else None,
            "_view": self._view_mode,
            "_filter": self.filter_panel.export_preset(),
        })
        self.workspace.save_state(state)

    def _schedule_state_save(self) -> None:
        if self.workspace:
            self._state_timer.start()

    def _create_samples(self) -> None:
        try:
            root = self.workspace.create_root("Vítejte v Task Master")
            root.set_field("_category", "Návod")
            root.set_field("_tags", ["ukázka", "návod"])
            root.write_body(
                "# Vítejte 👋\n\n"
                "Toto je **ukázkový úkol**.\n\n"
                "- Vlevo je strom úkolů a filtry\n"
                "- Vpravo metadata, *WYSIWYG* editor a odkazy\n"
                "- Soubory přidáš **přetažením** na úkol\n"
                "- Aplikace je plně ovladatelná klávesnicí (viz menu Nastavení → Klávesové zkratky)\n"
            )
            sub = root.create_child("První podúkol")
            sub.set_field("_status", "in_progress")
            sub.set_field("_priority", 8)
            sub.write_body("## Podúkol\n\nPodúkoly se ukládají jako podsložky.\n")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Naplnění stromu
    # ------------------------------------------------------------------
    def _match(self, node) -> bool:
        """Úkol je vidět, když vyhovuje filtru NEBO je právě aktivní.

        Tím zůstane nově vytvořený / právě upravený úkol zobrazený, i když
        nevyhovuje filtru – dokud je aktivní (vybraný).
        """
        return self.filter_panel.matches(node) or node is self._current_node

    # ------------------------------------------------------------------
    # Vícenásobný výběr (hromadné operace ve stromu / seznamu)
    # ------------------------------------------------------------------
    def _selected_nodes(self) -> list:
        """Úkoly pro operaci: víc označených jen když je mezi nimi i aktuální.

        Tím se běžný (jednotlivý) výběr chová jako dřív a hromadné operace se
        spustí jen při skutečném vícevýběru ve stromu/seznamu.
        """
        cur = self._current_node
        if self._view_mode in ("tree", "list"):
            ns = [n for n in self.tree.selected_nodes() if n is not None]
            if len(ns) > 1 and cur in ns:
                return ns
        elif self._view_mode == "cards":
            ns = [n for n in self.card_view.selected_nodes() if n is not None]
            if len(ns) > 1 and cur in ns:
                return ns
        return [cur] if cur is not None else []

    def _reselect(self, nodes) -> None:
        """Po přebudování zobrazení znovu označí dané uzly (jen strom/seznam)."""
        nodes = [n for n in nodes if n is not None]
        if not nodes:
            return
        if len(nodes) > 1 and self._view_mode in ("tree", "list"):
            self.tree.select_paths([n.path for n in nodes])
        elif len(nodes) > 1 and self._view_mode == "cards":
            self.card_view.select_paths([str(n.path) for n in nodes])
        else:
            self._select_in_view(nodes[0], focus=True)

    def _populate(self) -> None:
        if not self.workspace:
            return
        # automatické (od)blokování podle stavu podúkolů – před vykreslením,
        # ať se změny hned promítnou (idempotentní, když není co měnit)
        self._recompute_auto_blocks()
        sort_key, sort_desc = self.filter_panel.current_sort()
        if self._view_mode == "cards":
            self.stack.setCurrentWidget(self.card_view)
            self.card_view.populate(
                self._flat_sequence(),
                compact_fn=self._is_compact_card if self._compact_cards else None,
            )
        else:
            self.stack.setCurrentIndex(0)
            self.tree.populate(
                self.workspace.roots, self._view_mode == "tree", self._match,
                sort_key, sort_desc,
            )
        self.filter_panel.populate_dynamic(
            self.workspace.all_categories(), self.workspace.all_tags()
        )
        self._update_today_counts()

    def _flat_sequence(self, exclude=None) -> list:
        """Přesně to pořadí, v jakém úkoly stojí v plochém pohledu (seznam/karty).

        Jediný zdroj pravdy pro zobrazení i pro přesun v pořadí – kdyby se lišily,
        klávesová zkratka by úkol vkládala mezi jiné sousedy, než jaké uživatel vidí.
        """
        key, desc = self.filter_panel.current_sort()
        nodes = [n for n in self.workspace.all_nodes()
                 if n is not exclude and self._match(n)]
        seq = sort_flat(nodes, key, desc)
        if self._view_mode == "cards":
            # Bez rušení: seskup podle stavu do pevného pořadí skupin
            # (Probíhá+Ke zpracování → Čeká → Blokováno → Hotovo). Uvnitř skupiny
            # zůstane řazení z sort_flat (podúkol nad rodičem, blok pohromadě).
            seq.sort(key=self._group_index)
        return seq

    @staticmethod
    def _group_index(node) -> int:
        return STATUS_GROUP_INDEX.get(
            node.meta.get("_status", ""), len(STATUS_GROUPS)
        )

    @staticmethod
    def _is_compact_card(node) -> bool:
        """Úsporná (nižší) karta: vše mimo skupinu Probíhá+Ke zpracování."""
        return MainWindow._group_index(node) != 0

    def _on_filter_changed(self) -> None:
        self._populate()
        self._ensure_current_visible()
        self._schedule_state_save()

    def _ensure_current_visible(self) -> None:
        """Po změně filtru zajisti, že je vždy vybraný (zvýrazněný) nějaký úkol.

        Aktivní úkol zůstává zobrazený i když nevyhovuje filtru (viz _match),
        takže ho jen znovu označ. Pokud žádný aktivní není, vyber první vyhovující.
        Bez kradení klávesového fokusu (nebliká při psaní).
        """
        if not self.workspace:
            return
        cur = self._current_node
        if cur is not None and self.filter_panel.matches(cur):
            self._select_in_view(cur)
            return
        # po ZMĚNĚ FILTRU aktuální nevyhovuje -> přepni na první vyhovující
        # (a přebuduj, aby starý nevyhovující už nebyl držený jako aktivní)
        visible = [n for n in self.workspace.all_nodes() if self.filter_panel.matches(n)]
        key, desc = self.filter_panel.current_sort()
        self._current_node = sort_nodes(visible, key, desc)[0] if visible else None
        self._populate()
        if self._current_node is not None:
            self.detail.load(self._current_node)
            self._select_in_view(self._current_node)
        else:
            self.detail.load(None)

    def _reload(self) -> None:
        if not self.workspace:
            return
        sel = self._current_node
        sel_path = str(sel.path) if sel else None
        self.detail.commit()
        self.detail.discard()
        self._current_node = None
        self.workspace.load()
        self._populate()
        if sel_path:
            self._select_path_in_view(sel_path)

    # ------------------------------------------------------------------
    # Akce s úkoly
    # ------------------------------------------------------------------
    def _inherit_defaults(self, source) -> dict:
        """Zdědí od nadřazeného úkolu prioritu, vlaječku a kategorii.

        Z „sekčního" rodiče, jehož název začíná podtržítkem, se nedědí nic.
        """
        d = {}
        if source is not None and not source.title.startswith("_"):
            d["priority"] = source.meta.get("_priority", DEFAULT_PRIORITY)
            d["category"] = source.meta.get("_category", "") or ""
            d["flag"] = bool(source.meta.get("_flag", False))
        return d

    def _apply_dialog_meta(self, node, vals: dict) -> None:
        node.meta["_status"] = vals["status"]
        if vals["status"] == "done":
            node.meta.setdefault("_completed", now_iso())
        node.meta["_priority"] = vals["priority"]
        node.meta["_category"] = vals["category"]
        node.meta["_tags"] = vals["tags"]
        node.meta["_flag"] = vals["flag"]
        node.save_meta()

    def _new_task(self) -> None:
        if not self.workspace:
            return
        cur = self._current_node
        parent = cur.parent if cur is not None else None
        default_label = f"pod „{parent.title}“" if parent is not None else "nový kořenový úkol"
        vals = TaskDialog.get(
            self, "Nový úkol", self._inherit_defaults(parent or cur),
            roots=self.workspace.roots, default_label=default_label,
        )
        if not vals:
            return
        if vals.get("target"):
            self._create_under_target(vals["target"], vals)
            return
        self.detail.commit()
        self.detail.discard()
        if parent is not None:
            node = parent.create_child(vals["title"])
        else:
            node = self.workspace.create_root(vals["title"])
        self._apply_dialog_meta(node, vals)
        self.undo.push_created([node.task_id])
        self.workspace.normalize_orders()  # levné; bez plného načítání z disku
        # při výpočtu zařazení musí být aktuální úkol viditelný (viz _match)
        self._current_node = cur if cur is not None else node
        self._place_new_task(node, cur)
        self._current_node = node  # aktivní -> zobrazí se i mimo filtr
        self._populate()
        self._select_path_in_view(str(node.path))

    def _new_subtask(self) -> None:
        parent = self._current_node
        if parent is None:
            QMessageBox.information(self, "Podúkol", "Nejprve vyber nadřazený úkol.")
            return
        vals = TaskDialog.get(
            self, f"Nový podúkol pod „{parent.title}“", self._inherit_defaults(parent),
            roots=self.workspace.roots, default_label=f"pod „{parent.title}“",
        )
        if not vals:
            return
        if vals.get("target"):
            self._create_under_target(vals["target"], vals)
            return
        self.detail.commit()
        self.detail.discard()
        child = parent.create_child(vals["title"])
        self._apply_dialog_meta(child, vals)
        self.undo.push_created([child.task_id])
        self.workspace.normalize_orders()  # levné; bez plného načítání z disku
        # rodič musí být viditelný při výpočtu zařazení (viz _match)
        self._current_node = parent
        self._place_new_subtask(child, parent)
        self._current_node = child  # aktivní -> zobrazí se i mimo filtr
        self._populate()
        self._select_path_in_view(str(child.path))

    def _create_under_target(self, target_id: str, vals: dict) -> None:
        """Vytvoří úkol jako podúkol zvoleného cíle (na konec jeho podúkolů)."""
        tnode = self.workspace.node_by_id(target_id)
        if tnode is None:
            QMessageBox.warning(self, "Umístění", "Zvolený cílový úkol už neexistuje.")
            return
        self.detail.commit()
        self.detail.discard()
        child = tnode.create_child(vals["title"])
        self._apply_dialog_meta(child, vals)
        self.undo.push_created([child.task_id])
        self.workspace.normalize_orders()  # levné; bez plného načítání z disku
        self._current_node = child  # aktivní -> zobrazí se i mimo filtr
        self._populate()
        self._select_path_in_view(str(child.path))

    # ------------------------------------------------------------------
    # Schránka úkolů (copy / cut / paste / vložení z textu)
    # ------------------------------------------------------------------
    def _copy_task(self) -> None:
        node = self._current_node
        if node is None:
            return
        self._clip = {"mode": "copy", "data": serialize_node(node), "src_id": node.task_id}
        self.status.showMessage(f"Zkopírováno: {node.title}", 1500)

    def _cut_task(self) -> None:
        node = self._current_node
        if node is None:
            return
        self._clip = {"mode": "cut", "data": serialize_node(node), "src_id": node.task_id}
        self.status.showMessage(f"Vyjmuto: {node.title}", 1500)

    def _paste_task(self) -> None:
        if not self._clip or not self.workspace:
            return
        target = self._current_node  # vloží jako podúkol cíle (None = kořen)
        if self._clip["mode"] == "cut":
            src = self.workspace.node_by_id(self._clip["src_id"])
            if src is not None and target is not None and (src is target or src.is_ancestor_of(target)):
                QMessageBox.information(self, "Vložit", "Úkol nelze vložit do sebe sama.")
                return
        self.detail.commit()
        self.detail.discard()
        self._snapshot()
        new = self.workspace.create_subtree(target, self._clip["data"])
        new_id = new.meta.get("_id")
        was_cut = self._clip["mode"] == "cut"
        if was_cut:
            src = self.workspace.node_by_id(self._clip["src_id"])
            if src is not None:
                src.delete()
            self._clip = None  # vyjmutí je jednorázové
        self.workspace.load()
        # vyjmutí mění _id → úkoly blokované přesunutým osiřely, odblokuj je
        if was_cut:
            self.workspace.resolve_orphan_blocks()
        nn = self.workspace.node_by_id(new_id)
        if nn is not None:
            self._current_node = nn
        self._populate()
        if nn is not None:
            self._select_path_in_view(str(nn.path))

    def _paste_from_text(self) -> None:
        if not self.workspace:
            return
        text = QApplication.clipboard().text()
        roots = parse_indented_text(text)
        if not roots:
            QMessageBox.information(self, "Vložit z textu",
                                    "Schránka neobsahuje text se strukturou úkolů.")
            return
        cur = self._current_node
        pos = ask_paste_position(self, cur is not None)
        if pos is None:
            return
        self.detail.commit()
        self.detail.discard()
        self._snapshot()
        cur_id = cur.task_id if cur is not None else None
        if pos == "under":
            parent_node = cur
        elif pos == "after":
            parent_node = cur.parent if cur is not None else None
        else:  # end
            parent_node = None
        created_ids = []
        for r in roots:
            n = self.workspace.create_subtree(parent_node, r)
            created_ids.append(n.meta.get("_id"))
        self.workspace.load()
        if pos == "after" and cur_id:
            prev = self.workspace.node_by_id(cur_id)
            for cid in created_ids:
                nd = self.workspace.node_by_id(cid)
                if nd is not None and prev is not None and nd.parent is prev.parent:
                    self._place_node(nd, prev, before=False)
                    prev = nd
        first = self.workspace.node_by_id(created_ids[0]) if created_ids else None
        if first is not None:
            self._current_node = first
        self._populate()
        if first is not None:
            self._select_path_in_view(str(first.path))
        self.status.showMessage(f"Vloženo úkolů: {len(created_ids)}", 2000)

    def _show_tree_menu(self, pos) -> None:
        menu = QMenu(self)
        for cid in ("task.new", "task.new_sub", None,
                    "task.copy", "task.cut", "task.paste", "task.paste_text", None,
                    "task.rename", "task.delete", None, "task.flag", "task.toggle_done",
                    None, "edit.undo"):
            if cid is None:
                menu.addSeparator()
            else:
                menu.addAction(self.act[cid])
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    @staticmethod
    def _has_selected_ancestor(node, sel) -> bool:
        p = node.parent
        while p is not None:
            if p in sel:
                return True
            p = p.parent
        return False

    def _delete_task(self) -> None:
        nodes = self._selected_nodes()
        if not nodes:
            return
        # potomka, jehož předek je také označen, nemazat zvlášť (smaže se s předkem)
        sel = set(nodes)
        targets = [n for n in nodes if not self._has_selected_ancestor(n, sel)]
        if len(targets) == 1:
            node = targets[0]
            n_children = len(list(node.iter_descendants()))
            msg = f"Smazat úkol „{node.title}“"
            if n_children:
                msg += f" včetně {n_children} podúkolů"
            msg += "?\n\nSmaže se celá složka z disku."
        else:
            total = sum(1 + len(list(n.iter_descendants())) for n in targets)
            msg = (f"Smazat {len(targets)} úkolů (celkem {total} položek)?"
                   "\n\nSmažou se celé složky z disku.")
        if QMessageBox.question(self, "Smazat úkol", msg) != QMessageBox.StandardButton.Yes:
            return
        self.detail.discard()
        self._snapshot()
        for n in targets:
            n.delete()
        self._current_node = None
        self.detail.load(None)
        self.workspace.load()
        # úkoly blokované smazanými osiřely – odblokuj je (jinak uvíznou navždy)
        orphaned = self.workspace.resolve_orphan_blocks()
        self._populate()
        if orphaned:
            self.status.showMessage(
                f"Odblokováno úkolů po smazání: {len(orphaned)}", 3000
            )

    def _rename_dir(self) -> None:
        node = self._current_node
        if node is None:
            return
        if self._view_mode == "cards":
            self._set_view_mode("tree")
            self._select_in_view(node)
        self.tree.edit_title(node)

    def _on_rename(self, node, new_title: str) -> None:
        self.detail.commit()
        self.detail.discard()
        self._snapshot()
        try:
            node.rename_dir(new_title)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Chyba", f"Přejmenování selhalo:\n{e}")
        new_path = str(node.path)
        self.workspace.load()
        self._populate()
        self._select_path_in_view(new_path)

    def _on_reparent(self, node, new_parent) -> None:
        self.detail.commit()
        self.detail.discard()
        self._snapshot()
        try:
            if new_parent is None:
                self.workspace.move_to_root(node)
            else:
                node.move_to(new_parent.path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Chyba", f"Přesun selhal:\n{e}")
            return
        new_path = str(node.path)
        self.workspace.load()
        self._populate()
        self._select_path_in_view(new_path)

    # ------------------------------------------------------------------
    # Signály z panelů
    # ------------------------------------------------------------------
    def _drop_unpinned(self, prev, new) -> None:
        """Pokud předchozí (force-zobrazený) úkol nevyhovuje filtru, přebuduj
        zobrazení, aby po opuštění zmizel."""
        if prev is not None and prev is not new and not self.filter_panel.matches(prev):
            self._populate()
            if new is not None:
                self._select_in_view(new)

    def _on_task_selected(self, node) -> None:
        prev = self._current_node
        self._current_node = node
        self.detail.load(node)
        self._drop_unpinned(prev, node)
        self._schedule_state_save()

    def _on_card_selected(self, node) -> None:
        # výběr (i vícenásobný) si spravuje CardView sám; tady jen aktualizuj
        # aktuální úkol a detail (nepřenastavuj výběr, ať se nezruší vícevýběr)
        prev = self._current_node
        self._current_node = node
        self.card_view.setFocus()
        self.detail.load(node)
        self._drop_unpinned(prev, node)
        self._schedule_state_save()

    def _on_card_opened(self, node) -> None:
        self._current_node = node
        self._set_view_mode("tree")
        self._select_in_view(node)
        self._focus_editor()

    def _on_meta_changed(self, node) -> None:
        self._populate()

    def _on_status_meta_changed(self, node, status: str) -> None:
        """Stav změněný comboboxem v detailu: doptej se / odblokuj čekající."""
        if status == "blocked":
            self._ask_blocker(node)
            return
        if status == "done":
            unblocked = self._unblocked_by([node])
            if unblocked:
                self.undo.push_fields([(n.task_id, n.meta) for n in unblocked])
                for n in unblocked:
                    n.set_field("_status", "todo")
                self.status.showMessage(f"Odblokováno úkolů: {len(unblocked)}", 3000)
                self._populate()

    def _on_link_dropped(self, node) -> None:
        if self.detail.node is node:
            self.detail.refresh_links_external()
        self._populate()

    def _confirm_complete(self, node) -> bool:
        """Před označením úkolu za hotový potvrď, pokud má nedokončené podúkoly."""
        n = node.incomplete_subtasks()
        if n == 0:
            return True
        r = QMessageBox.question(
            self, "Dokončit úkol?",
            f"Úkol „{node.title}“ má {n} nedokončených podúkolů.\n"
            "Opravdu ho chceš označit jako hotový?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return r == QMessageBox.StandardButton.Yes

    def _confirm_complete_bulk(self, risky) -> bool:
        """Potvrzení pro hromadné dokončení úkolů s nedokončenými podúkoly."""
        if len(risky) == 1:
            return self._confirm_complete(risky[0])
        total = sum(n.incomplete_subtasks() for n in risky)
        r = QMessageBox.question(
            self, "Dokončit úkoly?",
            f"{len(risky)} úkolů má nedokončené podúkoly (celkem {total}).\n"
            "Opravdu je označit jako hotové?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return r == QMessageBox.StandardButton.Yes

    def _on_status_toggled(self, node, status: str) -> None:
        # z checkboxu / Ctrl+Enter: když je 'node' součástí vícevýběru, na všechny
        sel = self._selected_nodes()
        nodes = sel if (len(sel) > 1 and node in sel) else [node]
        self._apply_status_to(nodes, status)

    def _apply_status_to(self, nodes, status: str) -> None:
        if status == "done":
            risky = [n for n in nodes if n.incomplete_subtasks()]
            if risky and not self._confirm_complete_bulk(risky):
                # zrušeno – přebuduj z nezměněného stavu (vrátí zaškrtávátka zpět)
                QTimer.singleShot(0, self._populate)
                return
        # úkoly, které se dokončením těchto uzlů odblokují
        unblocked = self._unblocked_by(nodes) if status == "done" else []
        self.undo.push_fields(
            [(n.task_id, n.meta) for n in nodes]
            + [(n.task_id, n.meta) for n in unblocked]
        )
        for n in nodes:
            n.set_field("_status", status)
        for n in unblocked:
            n.set_field("_status", "todo")  # set_field zruší i _blocked_by
        if self.detail.node in nodes or self.detail.node in unblocked:
            self.detail.sync_status(self.detail.node.meta.get("_status"))
        if unblocked:
            self.status.showMessage(
                f"Odblokováno úkolů: {len(unblocked)}"
                + (f" – „{unblocked[0].title}“" if len(unblocked) == 1 else ""),
                3000,
            )
        going_done = status == "done"
        # přebudování odlož mimo právě probíhající itemChanged signál;
        # po dokončení skoč na první úkol a odroluj nahoru
        QTimer.singleShot(0, lambda: self._after_status_toggle(going_done))
        # na blokující úkol se zeptej až po přebudování (dialog nesmí běžet
        # uprostřed itemChanged signálu ze zaškrtávátka). Funguje i pro vícevýběr:
        # jeden dialog, zvolený blokující úkol se přiřadí všem označeným.
        if status == "blocked":
            blocked_nodes = list(nodes)
            QTimer.singleShot(0, lambda ns=blocked_nodes: self._ask_blocker(ns))

    def _unblocked_by(self, nodes) -> list:
        """Úkoly čekající na některý z `nodes` – dokončením se odblokují."""
        if not self.workspace:
            return []
        done_ids = {n.task_id for n in nodes if n.task_id}
        return [
            n for n in self.workspace.all_nodes()
            if n.blocked_by in done_ids and n not in nodes
        ]

    def _recompute_auto_blocks(self) -> list:
        """Automaticky (od)blokuje tasky podle stavu jejich přímých podúkolů.

        Task se zablokuje, když má aspoň jeden nedokončený přímý podúkol a všechny
        jeho nedokončené přímé podúkoly jsou ve stavu „čeká"/„blokováno" (přepíše
        i „probíhá"). Automaticky zablokovaný task se vrátí na „ke zpracování",
        jakmile podmínka přestane platit. Ruční blokování (bez příznaku
        _auto_blocked) se nepřepisuje.

        Běží do ustálení – změna potomka může vyvolat auto-blok rodiče a kaskádovat
        výš. Vrací změněné uzly (pro undo/hlášku).
        """
        if not self.workspace:
            return []
        changed = []
        for _ in range(64):  # strop proti teoretické oscilaci; reálně 1–2 průchody
            round_changed = []
            for n in self.workspace.all_nodes():
                st = n.meta.get("_status")
                if st == "done":
                    continue
                if n.should_auto_block():
                    # zablokuj jen aktivní (todo/probíhá) – ruční blocked nech být
                    if st in ("todo", "in_progress"):
                        n.set_field("_status", "blocked")
                        n.meta["_auto_blocked"] = True
                        n.save_meta()
                        round_changed.append(n)
                elif n.auto_blocked:
                    # podmínka pominula a blokoval to automat -> zpět na todo
                    n.set_field("_status", "todo")  # set_field smaže _auto_blocked
                    round_changed.append(n)
            if not round_changed:
                break
            changed.extend(round_changed)
        return changed

    def _ask_blocker(self, nodes) -> None:
        """Nabídne (nepovinně) blokující úkol; přiřadí ho všem `nodes`.

        Přijímá jeden uzel i seznam (vícevýběr). U vícevýběru se zeptá jednou
        a zvolený blokující úkol přiřadí všem, které jsou ještě ve stavu blocked.
        """
        if not self.workspace:
            return
        if not isinstance(nodes, (list, tuple)):
            nodes = [nodes]
        # ber jen ty, které opravdu skončily jako „blokováno"
        nodes = [n for n in nodes if n.meta.get("_status") == "blocked"]
        if not nodes:
            return
        selset = set(nodes)
        recent = [
            r for r in (self.workspace.node_by_id(i)
                        for i in self.workspace.recent_blockers())
            if r is not None and r not in selset
        ]
        # předvyplň vazbou, jen když ji všechny sdílejí (jinak nech prázdné)
        cur = {n.blocked_by for n in nodes}
        current_id = next(iter(cur)) if len(cur) == 1 else ""
        primary = nodes[0]
        chosen = BlockerDialog.get(
            self, primary, self.workspace.roots, recent, current_id, nodes=nodes
        )
        if chosen is None:
            return  # zrušeno – stav „blokováno" zůstává, jen bez vazby
        target = self.workspace.node_by_id(chosen) if chosen else None
        self.undo.push_fields([(n.task_id, n.meta) for n in nodes])
        # blokovat už hotovým úkolem by úkoly nechalo viset navždy (odblokovává
        # se až při jeho dokončení, které nikdy nepřijde) – rovnou je odblokuj
        if target is not None and target.meta.get("_status") == "done":
            for n in nodes:
                n.set_field("_status", "todo")
            if self.detail.node in selset:
                self.detail.sync_status("todo")
            self.status.showMessage(
                f"„{target.title}“ je hotový – "
                + ("úkoly jdou" if len(nodes) > 1 else "úkol jde") + " rovnou zpracovat",
                3000,
            )
            self._populate()
            self._reselect(nodes)
            return
        for n in nodes:
            n.set_blocked_by(chosen)
        if chosen:
            self.workspace.push_recent_blocker(chosen)
            if target is not None:
                msg = (f"Blokuje {len(nodes)} úkolů: {target.title}"
                       if len(nodes) > 1 else f"Blokuje: {target.title}")
                self.status.showMessage(msg, 3000)
        self._populate()
        self._reselect(nodes)

    def _after_status_toggle(self, going_done: bool) -> None:
        self._populate()
        if going_done:
            self._focus_first_task()

    def _focus_first_task(self) -> None:
        """Vybere první úkol v aktuálním zobrazení a odroluje nahoru."""
        if self._view_mode == "cards":
            if self.card_view._order:
                path = self.card_view._order[0]
                self.card_view.select_path(path)
                self.card_view.verticalScrollBar().setValue(0)
                self.card_view.setFocus()
                node = next((n for n in self.workspace.all_nodes() if str(n.path) == path), None)
                if node is not None:
                    self._current_node = node
                    self.detail.load(node)
        else:
            if self.tree.topLevelItemCount():
                it = self.tree.topLevelItem(0)
                self.tree.setCurrentItem(it)
                self.tree.verticalScrollBar().setValue(0)
                self.tree.setFocus()

    # ------------------------------------------------------------------
    # Odkazy mezi úkoly
    # ------------------------------------------------------------------
    def _navigate_to(self, node) -> None:
        if node is None:
            return
        if self._view_mode == "cards":
            self._set_view_mode("tree")
        if not self.tree.select_path(str(node.path)):
            # úkol je nejspíš odfiltrovaný – zruš filtry a zkus znovu
            self.filter_panel.reset()
            self.tree.select_path(str(node.path))
        self.tree.setFocus()

    def _add_ref_dialog(self) -> None:
        node = self.detail.node
        if node is None or not self.workspace:
            return
        candidates = [
            n for n in self.workspace.all_nodes()
            if n.task_id != node.task_id and n.task_id not in node.refs
        ]
        if not candidates:
            QMessageBox.information(self, "Odkaz na úkol", "Není žádný další úkol k propojení.")
            return
        labels = [breadcrumb(n) for n in candidates]
        choice, ok = QInputDialog.getItem(
            self, "Přidat odkaz na úkol", "Vyber úkol:", labels, 0, False
        )
        if not ok or not choice:
            return
        target = candidates[labels.index(choice)]
        if node.add_ref(target.task_id):
            self.detail.refresh_refs()
            self._populate()

    # ------------------------------------------------------------------
    # Uložené filtry
    # ------------------------------------------------------------------
    def _rebuild_filter_menu(self) -> None:
        for act in self._filter_actions:
            self.removeAction(act)
            act.deleteLater()
        self._filter_actions = []
        self.m_filters.clear()

        for sf in self.filter_store.filters:
            act = QAction(sf.name, self)
            if sf.shortcut:
                act.setShortcut(QKeySequence(sf.shortcut))
                act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            act.triggered.connect(lambda _checked=False, s=sf: self._apply_saved_filter(s))
            self.addAction(act)
            self.m_filters.addAction(act)
            self._filter_actions.append(act)

        if self.filter_store.filters:
            self.m_filters.addSeparator()
        self.m_filters.addAction(self.act["filter.save"])
        self.m_filters.addAction(self.act["filter.manage"])
        # combo uložených filtrů v panelu
        self.filter_panel.populate_saved([(f.id, f.name) for f in self.filter_store.filters])

    def _apply_saved_filter_by_id(self, fid: str) -> None:
        sf = self.filter_store.get(fid)
        if sf is not None:
            self._apply_saved_filter(sf)

    def _apply_saved_filter(self, sf: SavedFilter) -> None:
        self.detail.commit()
        self.filter_panel.apply_preset(sf.to_preset())
        self.filter_panel.set_saved(sf.id)
        view = sf.view if sf.view in VIEW_MODES else "tree"
        self._view_mode = view
        self.settings.setValue("view_mode", view)
        self.act_view[view].setChecked(True)
        self._populate()
        self._ensure_current_visible()
        self.status.showMessage(f"Filtr: {sf.name}", 2500)

    def _save_current_filter(self) -> None:
        name, ok = QInputDialog.getText(self, "Uložit aktuální filtr", "Název filtru:")
        if not ok or not name.strip():
            return
        sf = SavedFilter.from_preset(
            name.strip(), self.filter_panel.export_preset(), self._view_mode
        )
        self.filter_store.add(sf)
        self._rebuild_filter_menu()
        self.status.showMessage(f"Uložen filtr „{sf.name}“", 2500)

    def _manage_filters(self) -> None:
        reserved = {
            self.shortcuts.current(cid)
            for cid in COMMAND_DEFS
            if self.shortcuts.context(cid) == "window" and self.shortcuts.current(cid)
        }
        dlg = SavedFiltersDialog(
            self.filter_store,
            self.filter_panel.export_preset(),
            self._view_mode,
            reserved,
            self,
        )
        if dlg.exec():
            self._rebuild_filter_menu()

    # ------------------------------------------------------------------
    # Režimy zobrazení
    # ------------------------------------------------------------------
    def _set_view_mode(self, mode: str) -> None:
        if mode not in VIEW_MODES:
            return
        self.detail.commit()
        self._view_mode = mode
        self.settings.setValue("view_mode", mode)
        self.act_view[mode].setChecked(True)
        self._populate()
        # po přepnutí znovu označ aktuální úkol a vrať fokus do pohledu
        if self._current_node is not None:
            self._select_in_view(self._current_node)
        if mode == "cards":
            self.card_view.setFocus()
            self.card_view.ensure_selection()
        self._schedule_state_save()

    def _cycle_view(self) -> None:
        idx = VIEW_MODES.index(self._view_mode)
        self._set_view_mode(VIEW_MODES[(idx + 1) % len(VIEW_MODES)])

    def _toggle_compact_cards(self, checked: bool) -> None:
        self._compact_cards = bool(checked)
        self.settings.setValue("compact_cards", self._compact_cards)
        # zachovej výběr při přebudování karet
        cur = self._current_node
        self._populate()
        if cur is not None:
            self._select_in_view(cur)
        self.status.showMessage(
            "Úsporné karty: " + ("zapnuto" if checked else "vypnuto"), 1500
        )

    def _select_in_view(self, node, focus: bool = False) -> None:
        path = str(node.path)
        if self._view_mode == "cards":
            self.card_view.select_path(path)
            if focus:
                self.card_view.setFocus()
        else:
            self.tree.select_path(path)
            if focus:
                self.tree.setFocus()

    def _select_path_in_view(self, path: str) -> None:
        """Po strukturální změně označí úkol podle cesty v aktuálním pohledu."""
        if self._view_mode == "cards":
            node = next((n for n in self.workspace.all_nodes() if str(n.path) == path), None)
            if node is not None:
                self._current_node = node
                self.detail.load(node)
            self.card_view.select_path(path)
        else:
            self.tree.select_path(path)

    # ------------------------------------------------------------------
    # Vlastní pořadí (float -> vždy lze vložit mezi)
    # ------------------------------------------------------------------
    @staticmethod
    def _order_between(ordered, insert_at: int) -> float:
        """Pořadí (float) pro vložení na pozici v seznamu BEZ vkládaného uzlu."""
        prev = ordered[insert_at - 1].order if insert_at > 0 else None
        nxt = ordered[insert_at].order if insert_at < len(ordered) else None
        if prev is None and nxt is None:
            return 0.0
        if prev is None:
            return nxt - 1.0
        if nxt is None:
            return prev + 1.0
        if nxt - prev > 1e-9:
            return (prev + nxt) / 2.0
        # mezera vyčerpána -> přečísluj skupinu a vlož doprostřed
        for i, n in enumerate(ordered):
            n.set_order(float(i))
        return insert_at - 0.5

    def _place_node(self, dragged, ref, before: bool) -> None:
        siblings = ref.parent.children if ref.parent else self.workspace.roots
        ordered = sort_nodes(siblings, "order", False)
        if dragged in ordered:
            ordered.remove(dragged)
        if ref not in ordered:
            return
        idx = ordered.index(ref)
        insert_at = idx if before else idx + 1
        dragged.set_order(self._order_between(ordered, insert_at))

    # ----- zařazení nově vytvořeného úkolu (podle režimu zobrazení) -----
    def _visible_ordered(self, exclude=None) -> list:
        """Ploché zobrazené úkoly (seznam/karty) v tom pořadí, v jakém je vidět."""
        return self._flat_sequence(exclude=exclude)

    def _place_in_flat(self, node, ref, before: bool) -> None:
        """Nastaví pořadí uzlu tak, aby v plochém zobrazení stál hned za/před ref."""
        ordered = self._visible_ordered(exclude=node)
        if ref not in ordered:
            node.set_order(self.workspace.next_order())
            return
        idx = ordered.index(ref)
        insert_at = idx if before else idx + 1
        node.set_order(self._order_between(ordered, insert_at))

    def _place_new_task(self, new_node, cur_node) -> None:
        """Nový úkol: strom → hned za aktuální (sourozenec); jinak → pod aktuální."""
        if cur_node is None:
            return
        if self._view_mode == "tree":
            if cur_node.parent is new_node.parent:
                self._place_node(new_node, cur_node, before=False)
        else:
            self._place_in_flat(new_node, cur_node, before=False)

    def _place_new_subtask(self, new_node, parent_node) -> None:
        """Podúkol: strom → na konec podúkolů (řeší create_child); jinak →
        za poslední viditelný podúkol, nebo (nejsou-li) hned nad aktuální úkol."""
        if self._view_mode == "tree":
            return  # create_child už zařadil na konec přímých podúkolů
        ordered = self._visible_ordered(exclude=new_node)
        vis_desc = [n for n in parent_node.iter_descendants() if n in ordered]
        if vis_desc:
            last = max(vis_desc, key=ordered.index)
            self._place_in_flat(new_node, last, before=False)
        else:
            self._place_in_flat(new_node, parent_node, before=True)

    def _ensure_order_sort(self) -> None:
        if self.filter_panel.current_sort() != ("order", False):
            self.filter_panel.set_sort("order", False)

    def _move_task(self, delta: int) -> None:
        node = self._current_node
        if node is None or not self.workspace:
            return
        self._ensure_order_sort()
        sel = self._selected_nodes()
        if len(sel) > 1:
            self._move_selection(sel, delta)
            return
        # V plochém pohledu NELZE prohodit pořadí s vizuálním sousedem: ten bývá
        # rodič nebo úkol z cizí větve a jeho pozici drží hierarchie, ne _order
        # (prohození čísel by pak úkolem vůbec nepohnulo). Posouvej proto vždy
        # mezi sourozenci – to je jediné, co _order v plochém pohledu řídí.
        # Mezní stav si řeší _move_flat sám (na okraji skupiny povyšuje).
        if self._view_mode != "tree":
            self._move_flat(node, delta)
            return
        # strom: posun mezi sourozenci
        ordered = sort_nodes(
            node.parent.children if node.parent else self.workspace.roots,
            "order", False,
        )
        if node not in ordered or len(ordered) < 2:
            return
        idx = ordered.index(node)
        target = idx + delta
        if target < 0 or target >= len(ordered):
            return
        # vlož mezi vizuální sousedy (index do seznamu BEZ posouvaného uzlu):
        # po odebrání uzlu se indexy za ním posunou o 1 vlevo -> cíl je přímo `target`
        ordered_wo = [n for n in ordered if n is not node]
        insert_at = target
        # levné undo: _order_between může přečíslovat celou skupinu, ulož ji celou
        self.undo.push_fields((n.task_id, n.meta) for n in ordered)
        node.set_order(self._order_between(ordered_wo, insert_at))
        self._populate()
        self._select_in_view(node, focus=True)

    def _visible_siblings(self, node) -> list:
        """Viditelní sourozenci uzlu v plochém pohledu, seřazení podle pořadí.

        „Sourozenec" = uzel se stejným nejbližším VIDITELNÝM předkem; při
        odfiltrovaném rodiči se tak sourozenci stanou i uzly z vedlejší větve,
        které v seznamu skutečně sousedí.

        Skupina se určuje z hierarchie, ne ze zobrazené sekvence – v kartách
        totiž hotové úkoly padají dolů a skupinu by roztrhly.
        """
        present = {n for n in self.workspace.all_nodes() if self._match(n)}

        def vis_parent(n):
            p = n.parent
            while p is not None and p not in present:
                p = p.parent
            return p

        own = vis_parent(node)
        sibs = [n for n in present if vis_parent(n) is own]
        if self._view_mode == "cards":
            # Bez rušení řadí úkoly do skupin podle stavu – posouvej jen v rámci
            # té skupiny, ve které úkol stojí, ať nepřeskočí přes hranici skupiny
            g = self._group_index(node)
            sibs = [n for n in sibs if self._group_index(n) == g]
        key, desc = self.filter_panel.current_sort()
        return sort_nodes(sibs, key, desc)

    def _move_flat(self, node, delta: int) -> None:
        """Přesun v seznamu/kartách: o jednu pozici mezi viditelnými sourozenci.

        Posouvá se jen v rámci skupiny sourozenců – to je jediné, co vlastní
        pořadí v plochém pohledu určuje. Na okraji skupiny úkol zůstává: dál by
        se posunul jen změnou zanoření, a tu nesmí udělat šipka mlčky (od toho
        je přetažení myší nebo Vyjmout/Vložit).
        """
        sibs = self._visible_siblings(node)
        if node not in sibs or len(sibs) < 2:
            return
        idx = sibs.index(node)
        target = idx + delta
        if not (0 <= target < len(sibs)):
            where = "nahoře" if delta < 0 else "dole"
            parent = node.parent
            self.status.showMessage(
                f"Úkol je {where} ve svém bloku"
                + (f" (pod „{parent.title}“)" if parent is not None else ""),
                2000,
            )
            return
        other = sibs[target]
        self.undo.push_fields([(node.task_id, node.meta), (other.task_id, other.meta)])
        a, b = node.order, other.order
        if a == b:  # pojistka proti shodným číslům (stará data)
            self.workspace.normalize_orders()
            a, b = node.order, other.order
        node.set_order(b)
        other.set_order(a)
        self._populate()
        self._select_in_view(node, focus=True)

    def _move_selection(self, sel_nodes, delta: int) -> None:
        """Posune blok označených úkolů v pořadí nahoru/dolů (o jednu pozici).

        Ve stromu jen když všechny sdílejí stejného rodiče; v seznamu/kartách
        v celém plochém seznamu. Zachová relativní pořadí označených.
        """
        if self._view_mode == "tree":
            parents = {n.parent for n in sel_nodes}
            if len(parents) != 1:
                self.status.showMessage("Hromadný přesun jde jen mezi sourozenci", 2000)
                return
            p = next(iter(parents))
            seq = sort_nodes(p.children if p else self.workspace.roots, "order", False)
        else:
            seq = self._flat_sequence()
        selset = set(sel_nodes)
        if not any(n in selset for n in seq) or len(seq) < 2:
            return
        new_seq = list(seq)
        if delta < 0:
            for i in range(1, len(new_seq)):
                if new_seq[i] in selset and new_seq[i - 1] not in selset:
                    new_seq[i - 1], new_seq[i] = new_seq[i], new_seq[i - 1]
        else:
            for i in range(len(new_seq) - 2, -1, -1):
                if new_seq[i] in selset and new_seq[i + 1] not in selset:
                    new_seq[i], new_seq[i + 1] = new_seq[i + 1], new_seq[i]
        if new_seq == seq:
            return  # na kraji, nic se nezměnilo
        # levné undo pro celou skupinu; přerozděl stávající pořadová čísla
        self.undo.push_fields((n.task_id, n.meta) for n in seq)
        vals = sorted(n.order for n in seq)
        for n, val in zip(new_seq, vals):
            n.set_order(val)
        self._populate()
        self._reselect(sel_nodes)

    def _on_reorder(self, dragged, ref, before: bool) -> None:
        if dragged is None or ref is None or not self.workspace:
            return
        self.detail.commit()
        self.detail.discard()
        self._snapshot()
        dragged_id, ref_id = dragged.task_id, ref.task_id
        try:
            if dragged.parent is not ref.parent:
                if ref.parent is None:
                    self.workspace.move_to_root(dragged)
                else:
                    dragged.move_to(ref.parent.path)
                self.workspace.load()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Chyba", f"Přesun selhal:\n{e}")
            return
        dnode = self.workspace.node_by_id(dragged_id)
        rnode = self.workspace.node_by_id(ref_id)
        if dnode is None or rnode is None:
            self._populate()
            return
        self._place_node(dnode, rnode, before)
        self._ensure_order_sort()
        self._current_node = dnode
        self._populate()
        self._select_path_in_view(str(dnode.path))

    def _change_priority(self, delta: int) -> None:
        nodes = self._selected_nodes()
        if not nodes:
            return
        changed = []
        for n in nodes:
            try:
                p = int(n.meta.get("_priority", 5))
            except (TypeError, ValueError):
                p = 5
            new = max(1, min(10, p + delta))
            if new != p:
                changed.append((n, new))
        if not changed:
            return
        self.undo.push_fields([(n.task_id, n.meta) for n, _ in changed])
        for n, new in changed:
            n.set_field("_priority", new)
        if self.detail.node is not None and self.detail.node in nodes:
            self.detail.sync_priority(self.detail.node.meta.get("_priority"))
        self._populate()
        self._reselect(nodes)
        if len(changed) == 1:
            self.status.showMessage(f"Priorita: {changed[0][1]}", 1500)
        else:
            self.status.showMessage(f"Priorita změněna u {len(changed)} úkolů", 1500)

    # ------------------------------------------------------------------
    # Undo + přepnutí hotovo
    # ------------------------------------------------------------------
    def _snapshot(self) -> None:
        if self.workspace:
            self.undo.snapshot(self.workspace.root)

    def _undo(self) -> None:
        if not self.workspace or not self.undo.can_undo():
            self.status.showMessage("Není co vrátit", 1500)
            return
        sel = self._current_node
        sel_path = str(sel.path) if sel else None
        self.detail.discard()
        self.detail.load(None)
        self._current_node = None
        kind = self.undo.restore_last(self.workspace)
        if kind is None:
            self.status.showMessage("Vrácení selhalo", 1500)
            return
        if kind == "snapshot":
            self.workspace.load()  # disk se změnil vcelku
        # u „fields"/„created" je paměťový strom už konzistentní
        self._populate()
        if sel_path:
            self._select_path_in_view(sel_path)
        self.status.showMessage("Vráceno zpět", 1500)

    def _toggle_done(self) -> None:
        node = self._current_node
        if node is None:
            return
        # cíl podle aktuálního uzlu, aplikuj na celý výběr
        new = "todo" if node.meta.get("_status") == "done" else "done"
        self._apply_status_to(self._selected_nodes(), new)

    def _toggle_flag(self) -> None:
        nodes = self._selected_nodes()
        if not nodes:
            return
        # když jsou všechny označené s vlaječkou -> vypnout, jinak zapnout
        target = not all(n.flag for n in nodes)
        self.undo.push_fields([(n.task_id, n.meta) for n in nodes])
        for n in nodes:
            if n.flag != target:
                n.set_field("_flag", target)
        if self.detail.node in nodes:
            self.detail.sync_flag(self.detail.node.flag)
        self._populate()
        self._reselect(nodes)
        self.status.showMessage("Vlaječka: " + ("zapnuta" if target else "vypnuta"), 1500)

    def _on_sort_changed(self, prev_key, prev_desc, new_key, new_desc) -> None:
        # přepnutí na „vlastní pořadí" z jiného řazení -> přepiš pořadí podle
        # aktuálně zobrazeného uspořádání
        if new_key == "order" and prev_key != "order" and self.workspace:
            self._reseed_order(prev_key, prev_desc)
        self._populate()
        self._schedule_state_save()

    def _reseed_order(self, key: str, desc: bool) -> None:
        def reseed(nodes):
            for i, n in enumerate(sort_nodes(nodes, key, desc)):
                n.set_order(float(i))
        reseed(self.workspace.roots)
        for n in self.workspace.all_nodes():
            if n.children:
                reseed(n.children)

    def _save(self) -> None:
        self.detail.commit()
        self.status.showMessage("Uloženo", 1500)

    # ------------------------------------------------------------------
    # Stav okna
    # ------------------------------------------------------------------
    def _restore_geometry(self) -> None:
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)

    # ------------------------------------------------------------------
    # Responsivní rozložení: úzké/vysoké okno -> editor pod seznamem
    # ------------------------------------------------------------------
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_orientation()

    def _update_orientation(self) -> None:
        if not hasattr(self, "main_splitter"):
            return
        # úzké a vysoké okno (na výšku) -> editor pod seznamem
        want = (
            Qt.Orientation.Vertical
            if self.height() > self.width()
            else Qt.Orientation.Horizontal
        )
        if self.main_splitter.orientation() != want:
            self.main_splitter.setOrientation(want)
            if want == Qt.Orientation.Horizontal:
                self.main_splitter.setSizes([360, max(1, self.width() - 360)])
            else:
                self.main_splitter.setSizes([max(1, self.height() // 3),
                                             max(1, self.height() * 2 // 3)])

    def closeEvent(self, event) -> None:
        self.detail.commit()
        self._save_state()
        self.settings.setValue("geometry", self.saveGeometry())
        self.undo.cleanup()
        super().closeEvent(event)
