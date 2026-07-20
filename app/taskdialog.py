"""Dialogy: nový/upravený úkol s metadaty a volba pozice při vkládání."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .constants import DEFAULT_PRIORITY, DEFAULT_STATUS, PRIORITIES, STATUSES
from .tasktree import breadcrumb


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
        self.location_combo.addItem(f"⟐ {default_label}", None)
        for r in self._roots:
            if r.title.startswith("_"):
                self.location_combo.addItem(f"⌂ {r.title}", r.task_id)

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

        layout = QVBoxLayout(self)
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
        info.setStyleSheet("color:#555;")

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
