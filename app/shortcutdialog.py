"""Dialog pro konfiguraci klávesových zkratek."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from .shortcuts import COMMAND_DEFS, ShortcutManager

CID_ROLE = Qt.ItemDataRole.UserRole


class ShortcutDialog(QDialog):
    def __init__(self, manager: ShortcutManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Klávesové zkratky")
        self.resize(560, 560)

        info = QLabel(
            "Dvojklik (nebo výběr + zmáčknutí kombinace) změní zkratku.\n"
            "Editor a strom mají zkratky aktivní jen když jsou zaměřené."
        )
        info.setWordWrap(True)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Příkaz", "Zkratka"])
        self.tree.setRootIsDecorated(True)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemDoubleClicked.connect(lambda *_: self._edit_current())
        self.tree.itemSelectionChanged.connect(self._sync_editor)

        # editor pro zachycení kombinace
        self.key_edit = QKeySequenceEdit()
        self.key_edit.setMaximumSequenceLength(1)
        assign_btn = QPushButton("Přiřadit")
        clear_btn = QPushButton("Vymazat")
        reset_btn = QPushButton("Výchozí")
        assign_btn.clicked.connect(self._assign)
        clear_btn.clicked.connect(self._clear)
        reset_btn.clicked.connect(self._reset_one)

        edit_row = QHBoxLayout()
        edit_row.addWidget(QLabel("Nová kombinace:"))
        edit_row.addWidget(self.key_edit, 1)
        edit_row.addWidget(assign_btn)
        edit_row.addWidget(clear_btn)
        edit_row.addWidget(reset_btn)

        reset_all_btn = QPushButton("Obnovit vše na výchozí")
        reset_all_btn.clicked.connect(self._reset_all)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addWidget(self.tree, 1)
        layout.addLayout(edit_row)
        layout.addWidget(reset_all_btn)
        layout.addWidget(buttons)

        self._pending: dict[str, str] = dict(manager.overrides)
        self._build_rows()

    # ------------------------------------------------------------------
    def _build_rows(self) -> None:
        self.tree.clear()
        categories: dict[str, QTreeWidgetItem] = {}
        for cid, (label, category, _default, _ctx) in COMMAND_DEFS.items():
            if category not in categories:
                cat_item = QTreeWidgetItem([category, ""])
                cat_item.setFirstColumnSpanned(True)
                f = cat_item.font(0)
                f.setBold(True)
                cat_item.setFont(0, f)
                cat_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.tree.addTopLevelItem(cat_item)
                categories[category] = cat_item
            item = QTreeWidgetItem([label, self._seq_for(cid)])
            item.setData(0, CID_ROLE, cid)
            categories[category].addChild(item)
        self.tree.expandAll()

    def _seq_for(self, cid: str) -> str:
        return self._pending.get(cid, self.manager.default(cid))

    def _current_cid(self) -> str | None:
        item = self.tree.currentItem()
        return item.data(0, CID_ROLE) if item else None

    def _sync_editor(self) -> None:
        cid = self._current_cid()
        if cid:
            self.key_edit.setKeySequence(QKeySequence(self._seq_for(cid)))

    def _edit_current(self) -> None:
        if self._current_cid():
            self.key_edit.setFocus()
            self.key_edit.clear()

    def _refresh_row(self, cid: str) -> None:
        item = self.tree.currentItem()
        if item and item.data(0, CID_ROLE) == cid:
            item.setText(1, self._seq_for(cid))

    def _assign(self) -> None:
        cid = self._current_cid()
        if not cid:
            return
        seq = self.key_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        if not seq:
            return
        if seq == self.manager.default(cid):
            self._pending.pop(cid, None)
        else:
            self._pending[cid] = seq
        self._refresh_row(cid)

    def _clear(self) -> None:
        cid = self._current_cid()
        if not cid:
            return
        self._pending[cid] = ""
        self.key_edit.clear()
        self._refresh_row(cid)

    def _reset_one(self) -> None:
        cid = self._current_cid()
        if not cid:
            return
        self._pending.pop(cid, None)
        self._sync_editor()
        self._refresh_row(cid)

    def _reset_all(self) -> None:
        self._pending.clear()
        self._build_rows()
        self._sync_editor()

    def _save(self) -> None:
        # kontrola kolizí ve stejném kontextu
        seen: dict[tuple[str, str], str] = {}
        for cid in COMMAND_DEFS:
            seq = self._pending.get(cid, self.manager.default(cid))
            if not seq:
                continue
            ctx = self.manager.context(cid)
            key = (ctx, seq)
            if key in seen:
                ans = QMessageBox.question(
                    self,
                    "Kolize zkratek",
                    f"Zkratka „{seq}“ je přiřazena více příkazům "
                    f"(„{self.manager.label(seen[key])}“ a „{self.manager.label(cid)}“).\n\n"
                    "Uložit i tak?",
                )
                if ans != QMessageBox.StandardButton.Yes:
                    return
            else:
                seen[key] = cid

        # aplikuj
        self.manager.overrides = {k: v for k, v in self._pending.items()}
        for cid in COMMAND_DEFS:
            self.manager.set_shortcut(cid, self._pending.get(cid, self.manager.default(cid)))
        self.manager.save()
        self.accept()
