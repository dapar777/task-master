"""Konfigurace klávesových zkratek.

`ShortcutEditor` je vložitelný widget – sekce *Zkratky* dialogu nastavení
(`settingsdialog.py`). `ShortcutDialog` ho obalí pro samostatné použití.
"""

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
    QWidget,
)

from . import search
from .shortcuts import COMMAND_DEFS, ShortcutManager

CID_ROLE = Qt.ItemDataRole.UserRole


class ShortcutEditor(QWidget):
    """Strom příkazů se zkratkami + editor kombinace.

    Změny se drží v `_pending`, dokud se nezavolá `save()` – ta ohlídá kolize
    ve stejném kontextu, zapíše je do `ShortcutManager` a uloží soubor.
    """

    def __init__(self, manager: ShortcutManager, parent=None):
        super().__init__(parent)
        self.manager = manager

        info = QLabel(
            "Dvojklik (nebo výběr + zmáčknutí kombinace) změní zkratku.\n"
            "Editor a strom mají zkratky aktivní jen když jsou zaměřené."
        )
        info.setObjectName("hint")
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(info)
        layout.addWidget(self.tree, 1)
        layout.addLayout(edit_row)
        layout.addWidget(reset_all_btn)

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

    def filter_rows(self, query) -> int:
        """Skryje příkazy, které nesedí na dotaz (hledání v dialogu nastavení).

        `query` je text nebo `search.SearchQuery`; porovnává se popisek,
        kategorie i zkratka. Prázdný dotaz ukáže vše. Vrací počet viditelných
        příkazů.
        """
        q = search.parse(query) if isinstance(query, str) else query
        visible = 0
        for i in range(self.tree.topLevelItemCount()):
            cat = self.tree.topLevelItem(i)
            shown = 0
            for j in range(cat.childCount()):
                item = cat.child(j)
                hit = q.empty or q.matches(f"{cat.text(0)} {item.text(0)} {item.text(1)}")
                item.setHidden(not hit)
                shown += int(hit)
            cat.setHidden(shown == 0)
            visible += shown
        return visible

    def is_dirty(self) -> bool:
        return self._pending != self.manager.overrides

    def save(self) -> bool:
        """Zkontroluje kolize, aplikuje a uloží. Vrací False, když uživatel
        kolizi odmítl (volající pak nemá zavírat dialog)."""
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
                    return False
            else:
                seen[key] = cid

        self.manager.overrides = {k: v for k, v in self._pending.items()}
        for cid in COMMAND_DEFS:
            self.manager.set_shortcut(cid, self._pending.get(cid, self.manager.default(cid)))
        self.manager.save()
        return True


class ShortcutDialog(QDialog):
    """Samostatný dialog nad `ShortcutEditor` (Uložit / Zrušit)."""

    def __init__(self, manager: ShortcutManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Klávesové zkratky")
        self.resize(560, 560)
        self.editor = ShortcutEditor(manager, self)
        # zpětná kompatibilita pro testy a volající, kteří sahali na `tree`
        self.tree = self.editor.tree

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.editor, 1)
        layout.addWidget(buttons)

    def _save(self) -> None:
        if self.editor.save():
            self.accept()
