"""Dialogy: nový/upravený úkol s metadaty a volba pozice při vkládání."""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSlider,
    QSpinBox,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .constants import (
    DEFAULT_PRIORITY,
    DEFAULT_SNOOZE,
    DEFAULT_STATUS,
    PRIORITIES,
    SNOOZE_MAX_DAYS,
    STATUSES,
)
from . import theme
from .tasktree import breadcrumb


def format_duration(seconds: float) -> str:
    """Lidsky čitelná délka: „2 d 3 h", „45 min", „12 s"."""
    secs = int(max(0, seconds))
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return f"{d} d {h} h" if h else f"{d} d"
    if h:
        return f"{h} h {m} min" if m else f"{h} h"
    if m:
        return f"{m} min"
    return f"{s} s"


class TaskDialog(QDialog):
    """Dialog pro zadání úkolu i s metadaty."""

    def __init__(self, window_title="Nový úkol", defaults=None, parent=None,
                 roots=None, default_label="výchozí umístění"):
        super().__init__(parent)
        defaults = defaults or {}
        self.setWindowTitle(window_title)
        self.setMinimumWidth(380)
        self._roots = roots or []
        self._temp_idx = None  # dočasná položka „ze stromu" v comboboxu

        self.title_edit = QLineEdit(defaults.get("title", ""))
        self.title_edit.setPlaceholderText("název úkolu")

        self.status_combo = QComboBox()
        for k, v in STATUSES.items():
            self.status_combo.addItem(v, k)
        self._select(self.status_combo, defaults.get("status", DEFAULT_STATUS))

        self.priority_combo = QComboBox()
        for k, v in PRIORITIES.items():
            self.priority_combo.addItem(v, k)
        self._select(self.priority_combo, defaults.get("priority", DEFAULT_PRIORITY))

        self.category_edit = QLineEdit(defaults.get("category", "") or "")
        self.tags_edit = QLineEdit(", ".join(defaults.get("tags", []) or []))
        self.flag_check = QCheckBox("Vlaječka")
        self.flag_check.setChecked(bool(defaults.get("flag", False)))

        # výběr umístění nového úkolu (combobox: výchozí + top-level „_" úkoly)
        self.location_combo = QComboBox()
        self.location_combo.addItem(default_label, None)
        for r in self._roots:
            if r.title.startswith("_"):
                self.location_combo.addItem(r.title, r.task_id)

        form = QFormLayout()
        form.addRow("Název:", self.title_edit)
        form.addRow("Stav:", self.status_combo)
        form.addRow("Priorita:", self.priority_combo)
        form.addRow("Kategorie:", self.category_edit)
        form.addRow("Tagy:", self.tags_edit)
        form.addRow("", self.flag_check)
        form.addRow("Umístění (Ctrl+L):", self.location_combo)

        # rozklikávací výběr libovolné cesty ze stromu + textové hledání
        self.tree_toggle = QToolButton()
        self.tree_toggle.setText("Vybrat ze stromu ▸")
        self.tree_toggle.setCheckable(True)
        self.tree_toggle.setAutoRaise(True)
        self.tree_toggle.toggled.connect(self._toggle_tree)

        self.loc_search = QLineEdit()
        self.loc_search.setPlaceholderText("hledat v úkolech…")
        self.loc_search.textChanged.connect(self._filter_tree)
        self.loc_tree = QTreeWidget()
        self.loc_tree.setHeaderHidden(True)
        self.loc_tree.setMaximumHeight(220)
        for r in self._roots:
            self._add_tree_item(r, None)
        self.loc_tree.itemSelectionChanged.connect(self._on_tree_pick)

        self.loc_box = QWidget()
        loc_v = QVBoxLayout(self.loc_box)
        loc_v.setContentsMargins(0, 0, 0, 0)
        loc_v.addWidget(self.loc_search)
        loc_v.addWidget(self.loc_tree)
        self.loc_box.setVisible(False)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        # hlavička dialogu: název + kam se úkol zařadí
        heading = QLabel(window_title)
        heading.setFont(theme.title_font(14))
        sub = QLabel(f"Výchozí umístění: {default_label} · priorita, kategorie a vlaječka se dědí")
        sub.setObjectName("hint")
        sub.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(heading)
        layout.addWidget(sub)
        layout.addLayout(form)
        layout.addWidget(self.tree_toggle)
        layout.addWidget(self.loc_box)
        layout.addWidget(buttons)
        self.title_edit.setFocus()

        # klávesové zkratky pro metadata přímo v dialogu
        QShortcut(QKeySequence("Ctrl+T"), self, activated=self.flag_check.toggle)
        QShortcut(QKeySequence("Ctrl+Up"), self, activated=lambda: self._bump_priority(+1))
        QShortcut(QKeySequence("Ctrl+Down"), self, activated=lambda: self._bump_priority(-1))
        # zkratka pro rotaci umístění (další možnost při každém stisku)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._cycle_location)

    def _bump_priority(self, delta: int) -> None:
        i = self.priority_combo.currentIndex()
        i = max(0, min(self.priority_combo.count() - 1, i + delta))
        self.priority_combo.setCurrentIndex(i)

    # ----- výběr umístění -----
    def _cycle_location(self) -> None:
        """Ctrl+L: přepne na další možnost umístění (rotuje dokola)."""
        c = self.location_combo
        if c.count():
            c.setCurrentIndex((c.currentIndex() + 1) % c.count())

    def _add_tree_item(self, node, parent_item) -> None:
        it = QTreeWidgetItem([node.title])
        it.setData(0, Qt.ItemDataRole.UserRole, node)
        if parent_item is None:
            self.loc_tree.addTopLevelItem(it)
        else:
            parent_item.addChild(it)
        for c in node.children:
            self._add_tree_item(c, it)

    def _toggle_tree(self, on: bool) -> None:
        self.tree_toggle.setText("Vybrat ze stromu ▾" if on else "Vybrat ze stromu ▸")
        self.loc_box.setVisible(on)
        if on:
            self.loc_search.setFocus()
        self.adjustSize()

    def _on_tree_pick(self) -> None:
        items = self.loc_tree.selectedItems()
        if not items:
            return
        node = items[0].data(0, Qt.ItemDataRole.UserRole)
        if node is not None:
            self._select_target(node.task_id, breadcrumb(node))

    def _select_target(self, tid, text: str) -> None:
        """Vybere cíl v comboboxu; když tam ještě není, přidá dočasnou položku."""
        if self._temp_idx is not None:
            self.location_combo.removeItem(self._temp_idx)
            self._temp_idx = None
        idx = self.location_combo.findData(tid)
        if idx < 0:
            self.location_combo.addItem("↳ " + text, tid)
            idx = self.location_combo.count() - 1
            self._temp_idx = idx
        self.location_combo.setCurrentIndex(idx)

    def _filter_tree(self, text: str) -> None:
        q = text.strip().lower()

        def visit(item) -> bool:
            match = q in item.text(0).lower()
            child_vis = False
            for i in range(item.childCount()):
                child_vis = visit(item.child(i)) or child_vis
            visible = (not q) or match or child_vis
            item.setHidden(not visible)
            if q and child_vis:
                item.setExpanded(True)
            return visible

        for i in range(self.loc_tree.topLevelItemCount()):
            visit(self.loc_tree.topLevelItem(i))

    def showEvent(self, event):
        super().showEvent(event)
        # otevři vycentrovaně NAD rodičovským oknem
        par = self.parent()
        if par is not None:
            win = par.window()
            geo = win.frameGeometry()
            self.move(geo.center().x() - self.width() // 2,
                      geo.center().y() - self.height() // 2)

    def _select(self, combo: QComboBox, data) -> None:
        i = combo.findData(data)
        combo.setCurrentIndex(i if i >= 0 else 0)

    def values(self) -> dict:
        tags = [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]
        return {
            "title": self.title_edit.text().strip(),
            "status": self.status_combo.currentData(),
            "priority": self.priority_combo.currentData(),
            "category": self.category_edit.text().strip(),
            "tags": tags,
            "flag": self.flag_check.isChecked(),
            "target": self.location_combo.currentData(),  # None = výchozí umístění
        }

    @staticmethod
    def get(parent, window_title, defaults=None, roots=None,
            default_label="výchozí umístění") -> dict | None:
        dlg = TaskDialog(window_title, defaults, parent, roots, default_label)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vals = dlg.values()
            if vals["title"]:
                return vals
        return None


class BlockerDialog(QDialog):
    """Volba úkolu, který blokuje aktuální úkol (nepovinná).

    Nahoře combobox naposledy použitých blokujících úkolů, pod ním
    rozklikávací strom všech úkolů s hledáním.
    """

    def __init__(self, node, roots, recent, current_id="", parent=None,
                 nodes=None):
        super().__init__(parent)
        self.setWindowTitle("Blokující úkol")
        self.setMinimumWidth(420)
        self._roots = roots or []
        self._temp_idx = None
        # úkoly, které NEsmí být nabídnuty jako blokující (samy sebe / celý výběr)
        skip_nodes = list(nodes) if nodes else [node]

        if len(skip_nodes) > 1:
            info = QLabel(
                f"Co blokuje {len(skip_nodes)} označených úkolů?\n"
                "Zvolený úkol se přiřadí všem. Výběr je nepovinný."
            )
        else:
            info = QLabel(f"Co blokuje úkol „{node.title}“?\nVýběr je nepovinný.")
        info.setObjectName("hint")

        # combobox: žádný + naposledy použité blokující úkoly
        self.blocker_combo = QComboBox()
        self.blocker_combo.addItem("— nic konkrétního —", "")
        for n in recent:
            self.blocker_combo.addItem(f"↺ {breadcrumb(n)}", n.task_id)

        form = QFormLayout()
        form.addRow("Blokuje mě:", self.blocker_combo)

        # rozklikávací strom všech úkolů
        self.tree_toggle = QToolButton()
        self.tree_toggle.setText("Vybrat ze stromu ▸")
        self.tree_toggle.setCheckable(True)
        self.tree_toggle.setAutoRaise(True)
        self.tree_toggle.toggled.connect(self._toggle_tree)

        self.search = QLineEdit()
        self.search.setPlaceholderText("hledat v úkolech…")
        self.search.textChanged.connect(self._filter_tree)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMaximumHeight(240)
        self._skip = set(skip_nodes)
        for r in self._roots:
            self._add_tree_item(r, None)
        self.tree.itemSelectionChanged.connect(self._on_tree_pick)

        self.tree_box = QWidget()
        tv = QVBoxLayout(self.tree_box)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.addWidget(self.search)
        tv.addWidget(self.tree)
        self.tree_box.setVisible(False)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Uložit")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Zrušit")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addLayout(form)
        layout.addWidget(self.tree_toggle)
        layout.addWidget(self.tree_box)
        layout.addWidget(buttons)

        if current_id:
            i = self.blocker_combo.findData(current_id)
            if i >= 0:
                self.blocker_combo.setCurrentIndex(i)
        self.blocker_combo.setFocus()

    def _add_tree_item(self, node, parent_item) -> None:
        # vynechané úkoly (samy sebe / celý vícevýběr) nesmí blokovat – vynech
        # JEN je, ne celý podstrom (jejich podúkoly klidně blokovat mohou, proto
        # se přivěsí o úroveň výš k rodiči vynechaného úkolu)
        if node in self._skip:
            for c in node.children:
                self._add_tree_item(c, parent_item)
            return
        done = node.meta.get("_status") == "done"
        it = QTreeWidgetItem([node.title + ("  (hotovo)" if done else "")])
        it.setData(0, Qt.ItemDataRole.UserRole, node)
        if done:
            # hotový úkol blokovat může, ale nedává to smysl – zbytek jde vybrat
            it.setForeground(0, Qt.GlobalColor.gray)
            it.setToolTip(0, "Úkol je hotový – blokovat jím nedává smysl")
        if parent_item is None:
            self.tree.addTopLevelItem(it)
        else:
            parent_item.addChild(it)
        for c in node.children:
            self._add_tree_item(c, it)

    def _toggle_tree(self, on: bool) -> None:
        self.tree_toggle.setText("Vybrat ze stromu ▾" if on else "Vybrat ze stromu ▸")
        self.tree_box.setVisible(on)
        if on:
            self.tree.expandAll()  # ať jsou vidět i vnořené úkoly
            self.search.setFocus()
        self.adjustSize()

    def _on_tree_pick(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        node = items[0].data(0, Qt.ItemDataRole.UserRole)
        if node is None:
            return
        tid = node.task_id
        if self._temp_idx is not None:
            self.blocker_combo.removeItem(self._temp_idx)
            self._temp_idx = None
        idx = self.blocker_combo.findData(tid)
        if idx < 0:
            self.blocker_combo.addItem("↳ " + breadcrumb(node), tid)
            idx = self.blocker_combo.count() - 1
            self._temp_idx = idx
        self.blocker_combo.setCurrentIndex(idx)

    def _filter_tree(self, text: str) -> None:
        q = text.strip().lower()

        def visit(item) -> bool:
            match = q in item.text(0).lower()
            child_vis = False
            for i in range(item.childCount()):
                child_vis = visit(item.child(i)) or child_vis
            visible = (not q) or match or child_vis
            item.setHidden(not visible)
            if q and child_vis:
                item.setExpanded(True)
            return visible

        for i in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(i))

    def showEvent(self, event):
        super().showEvent(event)
        par = self.parent()
        if par is not None:
            geo = par.window().frameGeometry()
            self.move(geo.center().x() - self.width() // 2,
                      geo.center().y() - self.height() // 2)

    @staticmethod
    def get(parent, node, roots, recent, current_id="", nodes=None) -> str | None:
        """Vrátí _id blokujícího úkolu ("" = žádný), None = zrušeno.

        Pro vícevýběr předej `nodes` – dialog vyloučí všechny z nabídky a
        vrácené _id se přiřadí všem.
        """
        dlg = BlockerDialog(node, roots, recent, current_id, parent, nodes=nodes)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.blocker_combo.currentData() or ""
        return None


def ask_paste_position(parent, has_current: bool) -> str | None:
    """Vrátí 'under' | 'after' | 'end' | None (zrušeno)."""
    box = QMessageBox(parent)
    box.setWindowTitle("Vložit úkoly z textu")
    box.setText("Kam vložit úkoly?")
    btn_end = box.addButton("Na konec", QMessageBox.ButtonRole.AcceptRole)
    btn_under = None
    btn_after = None
    if has_current:
        btn_under = box.addButton("Pod aktuální", QMessageBox.ButtonRole.AcceptRole)
        btn_after = box.addButton("Za aktuální", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Zrušit", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    clicked = box.clickedButton()
    if clicked is btn_under:
        return "under"
    if clicked is btn_after:
        return "after"
    if clicked is btn_end:
        return "end"
    return None


class SequenceDialog(QDialog):
    """Potvrzení a úprava pořadí při vytváření sekvence úkolů.

    Sekvence = řetěz blokování: druhý úkol čeká na první, třetí na druhý atd.
    Pořadí jde přeskládat tlačítky nebo tažením; položku lze i vyřadit.
    """

    def __init__(self, nodes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vytvořit sekvenci")
        self.setMinimumWidth(460)

        info = QLabel(
            "Úkoly se zřetězí v tomto pořadí – každý bude blokovaný tím "
            "předchozím. První zůstane volný a jak ho dokončíš, odemkne se "
            "další."
        )
        info.setWordWrap(True)
        info.setObjectName("hint")

        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for n in nodes:
            it = QListWidgetItem(breadcrumb(n))
            it.setData(Qt.ItemDataRole.UserRole, n)
            self.list.addItem(it)
        self.list.setCurrentRow(0)
        self.list.model().rowsMoved.connect(self._renumber)
        self.list.model().rowsRemoved.connect(self._renumber)

        up = QToolButton(); up.setText("▲"); up.setToolTip("Posunout nahoru")
        down = QToolButton(); down.setText("▼"); down.setToolTip("Posunout dolů")
        rm = QToolButton(); rm.setText("✕"); rm.setToolTip("Vyřadit ze sekvence")
        up.clicked.connect(lambda: self._move(-1))
        down.clicked.connect(lambda: self._move(1))
        rm.clicked.connect(self._remove)

        side = QVBoxLayout()
        side.addWidget(up); side.addWidget(down)
        side.addSpacing(8); side.addWidget(rm)
        side.addStretch(1)

        row = QHBoxLayout()
        row.addWidget(self.list, 1)
        row.addLayout(side)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setObjectName("faintLabel")

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Vytvořit sekvenci")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(info)
        lay.addLayout(row)
        lay.addWidget(self.summary)
        lay.addWidget(self.buttons)
        self._renumber()

    # ----- pořadí -----
    def _move(self, delta: int) -> None:
        r = self.list.currentRow()
        t = r + delta
        if r < 0 or not (0 <= t < self.list.count()):
            return
        self.list.insertItem(t, self.list.takeItem(r))
        self.list.setCurrentRow(t)
        self._renumber()

    def _remove(self) -> None:
        r = self.list.currentRow()
        if r >= 0:
            self.list.takeItem(r)
            self._renumber()

    def _renumber(self, *_args) -> None:
        """Přečísluje popisky a shrne, co se stane; míň než 2 úkoly nedávají smysl."""
        for i in range(self.list.count()):
            it = self.list.item(i)
            n = it.data(Qt.ItemDataRole.UserRole)
            it.setText(f"{i + 1}.  {breadcrumb(n)}")
        cnt = self.list.count()
        if cnt >= 2:
            first = self.list.item(0).data(Qt.ItemDataRole.UserRole)
            self.summary.setText(
                f"Zřetězí se {cnt} úkolů; volný zůstane „{first.title}“, "
                f"zbylých {cnt - 1} se zablokuje."
            )
        else:
            self.summary.setText("Sekvence potřebuje aspoň dva úkoly.")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(cnt >= 2)

    def nodes(self) -> list:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.list.count())]

    @staticmethod
    def get(parent, nodes) -> list | None:
        """Vrátí úkoly v potvrzeném pořadí, nebo None při zrušení."""
        dlg = SequenceDialog(nodes, parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            out = dlg.nodes()
            return out if len(out) >= 2 else None
        return None


class SnoozeDialog(QDialog):
    """Volba intervalu odkladu – posuvníky na dny, hodiny a minuty.

    Předvyplní se naposledy použitá hodnota (viz DEFAULT_SNOOZE pro první
    použití). Vrací počet sekund.
    """

    def __init__(self, node=None, initial=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Čekat do…")
        self.setMinimumWidth(420)
        d, h, m = initial or DEFAULT_SNOOZE

        if node is not None:
            info = QLabel(f"Za jak dlouho se má „{node.title}“ znovu ozvat?")
        else:
            info = QLabel("Za jak dlouho se mají úkoly znovu ozvat?")
        info.setWordWrap(True)
        info.setObjectName("hint")

        form = QFormLayout()
        self._sliders = {}
        for key, label, maximum, value in (
            ("days", "Dny", SNOOZE_MAX_DAYS, d),
            ("hours", "Hodiny", 23, h),
            ("minutes", "Minuty", 59, m),
        ):
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(0, maximum)
            sl.setValue(int(value))
            sl.setPageStep(1)
            num = QSpinBox()
            num.setRange(0, maximum)
            num.setValue(int(value))
            # posuvník a číslo drží stejnou hodnotu (psaní i tažení)
            sl.valueChanged.connect(num.setValue)
            num.valueChanged.connect(sl.setValue)
            sl.valueChanged.connect(self._update_summary)
            row = QHBoxLayout()
            row.addWidget(sl, 1)
            row.addWidget(num)
            wrap = QWidget()
            wrap.setLayout(row)
            form.addRow(label, wrap)
            self._sliders[key] = sl

        self.summary = QLabel()
        self.summary.setObjectName("hint")

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Odložit")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(info)
        lay.addLayout(form)
        lay.addWidget(self.summary)
        lay.addWidget(self.buttons)
        self._update_summary()

    # ----- hodnoty -----
    def parts(self) -> tuple[int, int, int]:
        return (self._sliders["days"].value(),
                self._sliders["hours"].value(),
                self._sliders["minutes"].value())

    def seconds(self) -> int:
        d, h, m = self.parts()
        return d * 86400 + h * 3600 + m * 60

    def _update_summary(self, *_a) -> None:
        secs = self.seconds()
        if secs <= 0:
            self.summary.setText("Nastav aspoň minutu.")
        else:
            when = datetime.now() + timedelta(seconds=secs)
            self.summary.setText(
                f"Ozve se za {format_duration(secs)}  ·  {when.strftime('%d.%m. %H:%M')}"
            )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(secs > 0)

    @staticmethod
    def get(parent, node=None, initial=None) -> int | None:
        """Vrátí délku odkladu v sekundách, nebo None při zrušení."""
        dlg = SnoozeDialog(node, initial, parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            secs = dlg.seconds()
            return secs if secs > 0 else None
        return None
