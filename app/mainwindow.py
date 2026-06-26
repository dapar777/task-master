"""Hlavní okno aplikace Task Master."""

from __future__ import annotations

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
from .constants import APP_NAME, DEFAULT_PRIORITY, ORG_NAME
from .detailpanel import TaskDetailPanel
from .filterpanel import FilterPanel
from .savedfilters import FilterStore, SavedFilter
from .savedfiltersdialog import SavedFiltersDialog
from .shortcutdialog import ShortcutDialog
from .shortcuts import COMMAND_DEFS, ShortcutManager
from .storage import Workspace, parse_indented_text, serialize_node
from .taskdialog import TaskDialog, ask_paste_position
from .undo import UndoManager
from .tasktree import TaskTreeWidget, breadcrumb, sort_nodes

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
        state = {
            "_active": self._current_node.meta.get("_id") if self._current_node else None,
            "_view": self._view_mode,
            "_filter": self.filter_panel.export_preset(),
        }
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
    def _populate(self) -> None:
        if not self.workspace:
            return
        sort_key, sort_desc = self.filter_panel.current_sort()
        if self._view_mode == "cards":
            self.stack.setCurrentWidget(self.card_view)
            nodes = [n for n in self.workspace.all_nodes() if self.filter_panel.matches(n)]
            nodes = sort_nodes(nodes, sort_key, sort_desc)
            # v režimu Bez rušení řadíme dokončené úkoly až za nedokončené (stabilně)
            nodes.sort(key=lambda n: n.meta.get("_status") == "done")
            self.card_view.populate(nodes)
        else:
            self.stack.setCurrentIndex(0)
            self.tree.populate(
                self.workspace.roots, self._view_mode == "tree", self.filter_panel.matches,
                sort_key, sort_desc,
            )
        self.filter_panel.populate_dynamic(
            self.workspace.all_categories(), self.workspace.all_tags()
        )

    def _on_filter_changed(self) -> None:
        self._populate()
        self._ensure_current_visible()
        self._schedule_state_save()

    def _ensure_current_visible(self) -> None:
        """Po změně filtru: pokud aktuální úkol nevyhovuje, vyber první vyhovující."""
        if not self.workspace:
            return
        cur = self._current_node
        if cur is not None and self.filter_panel.matches(cur):
            return
        visible = [n for n in self.workspace.all_nodes() if self.filter_panel.matches(n)]
        if visible:
            key, desc = self.filter_panel.current_sort()
            first = sort_nodes(visible, key, desc)[0]
            self._current_node = first
            self.detail.load(first)
            self._select_in_view(first)
        else:
            self._current_node = None
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
        d = {}
        if source is not None:
            d["priority"] = source.meta.get("_priority", DEFAULT_PRIORITY)
            d["category"] = source.meta.get("_category", "") or ""
        return d

    def _apply_dialog_meta(self, node, vals: dict) -> None:
        node.meta["_status"] = vals["status"]
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
        vals = TaskDialog.get(self, "Nový úkol", self._inherit_defaults(parent or cur))
        if not vals:
            return
        self.detail.commit()
        self.detail.discard()
        self._snapshot()
        if parent is not None:
            node = parent.create_child(vals["title"])
        else:
            node = self.workspace.create_root(vals["title"])
        self._apply_dialog_meta(node, vals)
        new_id = node.meta.get("_id")
        cur_id = cur.meta.get("_id") if cur is not None else None
        self.workspace.load()
        nn = self.workspace.node_by_id(new_id)
        if nn is not None and cur_id:
            cu = self.workspace.node_by_id(cur_id)
            if cu is not None and cu.parent is nn.parent:
                self._place_node(nn, cu, before=False)
        self._populate()
        if nn is not None:
            self._select_path_in_view(str(nn.path))

    def _new_subtask(self) -> None:
        parent = self._current_node
        if parent is None:
            QMessageBox.information(self, "Podúkol", "Nejprve vyber nadřazený úkol.")
            return
        vals = TaskDialog.get(self, f"Nový podúkol pod „{parent.title}“", self._inherit_defaults(parent))
        if not vals:
            return
        self.detail.commit()
        self.detail.discard()
        self._snapshot()
        child = parent.create_child(vals["title"])
        self._apply_dialog_meta(child, vals)
        new_id = child.meta.get("_id")
        self.workspace.load()
        nn = self.workspace.node_by_id(new_id)
        self._populate()
        if nn is not None:
            self._select_path_in_view(str(nn.path))

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
        if self._clip["mode"] == "cut":
            src = self.workspace.node_by_id(self._clip["src_id"])
            if src is not None:
                src.delete()
            self._clip = None  # vyjmutí je jednorázové
        self.workspace.load()
        self._populate()
        nn = self.workspace.node_by_id(new_id)
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
        self._populate()
        if created_ids:
            first = self.workspace.node_by_id(created_ids[0])
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

    def _delete_task(self) -> None:
        node = self._current_node
        if node is None:
            return
        n_children = len(list(node.iter_descendants()))
        msg = f"Smazat úkol „{node.title}“"
        if n_children:
            msg += f" včetně {n_children} podúkolů"
        msg += "?\n\nSmaže se celá složka z disku."
        if QMessageBox.question(self, "Smazat úkol", msg) != QMessageBox.StandardButton.Yes:
            return
        self.detail.discard()
        self._snapshot()
        node.delete()
        self._current_node = None
        self.detail.load(None)
        self.workspace.load()
        self._populate()

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
    def _on_task_selected(self, node) -> None:
        self._current_node = node
        self.detail.load(node)
        self._schedule_state_save()

    def _on_card_selected(self, node) -> None:
        self._current_node = node
        self.card_view.select_path(str(node.path))
        self.card_view.setFocus()
        self.detail.load(node)
        self._schedule_state_save()

    def _on_card_opened(self, node) -> None:
        self._current_node = node
        self._set_view_mode("tree")
        self._select_in_view(node)
        self._focus_editor()

    def _on_meta_changed(self, node) -> None:
        self._populate()

    def _on_link_dropped(self, node) -> None:
        if self.detail.node is node:
            self.detail.refresh_links_external()
        self._populate()

    def _on_status_toggled(self, node, status: str) -> None:
        self._snapshot()
        node.set_field("_status", status)
        if self.detail.node is node:
            self.detail.sync_status(status)
        # přebudování stromu odlož mimo právě probíhající itemChanged signál
        QTimer.singleShot(0, self._populate)

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

    def _ensure_order_sort(self) -> None:
        if self.filter_panel.current_sort() != ("order", False):
            self.filter_panel.set_sort("order", False)

    def _move_task(self, delta: int) -> None:
        node = self._current_node
        if node is None or not self.workspace:
            return
        self._ensure_order_sort()
        # posouváme v rámci aktuálně ZOBRAZENÉ posloupnosti:
        #  - strom: mezi sourozenci, - seznam/karty: v celém plochém seznamu
        if self._view_mode == "tree":
            seq = node.parent.children if node.parent else self.workspace.roots
        else:
            seq = [n for n in self.workspace.all_nodes() if self.filter_panel.matches(n)]
        ordered = sort_nodes(seq, "order", False)
        if node not in ordered or len(ordered) < 2:
            return
        idx = ordered.index(node)
        target = idx + delta
        if target < 0 or target >= len(ordered):
            return
        # vlož mezi vizuální sousedy (změní jen číslo pořadí, bez přeřazení rodiče)
        ordered_wo = [n for n in ordered if n is not node]
        insert_at = idx - 1 if delta < 0 else idx + 1
        self._snapshot()
        node.set_order(self._order_between(ordered_wo, insert_at))
        self._populate()
        self._select_in_view(node, focus=True)

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
        node = self._current_node
        if node is None:
            return
        try:
            p = int(node.meta.get("_priority", 5))
        except (TypeError, ValueError):
            p = 5
        new = max(1, min(10, p + delta))
        if new == p:
            return
        self._snapshot()
        node.set_field("_priority", new)
        if self.detail.node is node:
            self.detail.sync_priority(new)
        self._populate()
        self._select_in_view(node, focus=True)
        self.status.showMessage(f"Priorita: {new}", 1500)

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
        if self.undo.restore_last(self.workspace.root):
            self.workspace.load()
            self._populate()
            if sel_path:
                self._select_path_in_view(sel_path)
            self.status.showMessage("Vráceno zpět", 1500)

    def _toggle_done(self) -> None:
        node = self._current_node
        if node is None:
            return
        new = "todo" if node.meta.get("_status") == "done" else "done"
        self._on_status_toggled(node, new)

    def _toggle_flag(self) -> None:
        node = self._current_node
        if node is None:
            return
        self._snapshot()
        state = node.toggle_flag()
        if self.detail.node is node:
            self.detail.sync_flag(state)
        self._populate()
        self._select_in_view(node)
        self.status.showMessage("Vlaječka: " + ("zapnuta" if state else "vypnuta"), 1500)

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
