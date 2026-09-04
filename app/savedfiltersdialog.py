"""Dialog pro správu uložených filtrů (presetů)."""

from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .constants import PRIORITIES, SORT_OPTIONS, STATUSES
from .savedfilters import FilterStore, SavedFilter


def summary(sf: SavedFilter) -> str:
    parts = []
    if sf.name_text:
        parts.append(f"název~„{sf.name_text}“")
    if sf.statuses:
        parts.append("stav=" + ", ".join(STATUSES.get(s, s) for s in sf.statuses))
    if sf.priority_min > 1 or sf.priority_max < 10:
        parts.append(f"priorita {sf.priority_min}–{sf.priority_max}")
    if sf.categories:
        parts.append("kategorie=" + ", ".join(sf.categories))
    if sf.tags:
        parts.append("tagy=" + ", ".join(sf.tags))
    if sf.flag is True:
        parts.append("🚩 označené")
    elif sf.flag is False:
        parts.append("bez vlaječky")
    return ", ".join(parts) if parts else "(bez podmínek – zobrazí vše)"


class SavedFiltersDialog(QDialog):
    def __init__(self, store: FilterStore, current_preset: dict, current_view: str,
                 reserved_shortcuts: set[str], parent=None):
        super().__init__(parent)
        self.store = store
        self.current_preset = current_preset
        self.current_view = current_view
        self.reserved = reserved_shortcuts
        self.working: list[SavedFilter] = copy.deepcopy(store.filters)
        self._current: SavedFilter | None = None

        self.setWindowTitle("Uložené filtry")
        self.resize(680, 460)

        # levý sloupec – seznam
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_row_changed)
        new_btn = QPushButton("Nový z aktuálního")
        del_btn = QPushButton("Smazat")
        new_btn.clicked.connect(self._new_from_current)
        del_btn.clicked.connect(self._delete)
        left_btns = QHBoxLayout()
        left_btns.addWidget(new_btn)
        left_btns.addWidget(del_btn)
        left = QVBoxLayout()
        left.addWidget(QLabel("Filtry:"))
        left.addWidget(self.list, 1)
        left.addLayout(left_btns)

        # pravý sloupec – editor
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._on_name_changed)
        self.view_combo = QComboBox()
        self.view_combo.addItem("Strom", "tree")
        self.view_combo.addItem("Seznam", "list")
        self.view_combo.addItem("Bez rušení (karty)", "cards")
        self.sort_combo = QComboBox()
        for k, v in SORT_OPTIONS.items():
            self.sort_combo.addItem(v, k)
        self.dir_combo = QComboBox()
        self.dir_combo.addItem("Vzestupně ↑", False)
        self.dir_combo.addItem("Sestupně ↓", True)
        self.key_edit = QKeySequenceEdit()
        self.key_edit.setMaximumSequenceLength(1)
        key_clear = QPushButton("Vymazat")
        key_clear.clicked.connect(self.key_edit.clear)
        key_row = QHBoxLayout()
        key_row.addWidget(self.key_edit, 1)
        key_row.addWidget(key_clear)

        form = QFormLayout()
        form.addRow("Název:", self.name_edit)
        form.addRow("Zobrazení:", self.view_combo)
        form.addRow("Řadit dle:", self.sort_combo)
        form.addRow("Směr:", self.dir_combo)
        form.addRow("Zkratka:", key_row)

        self.summary_label = QLabel("—")
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName("hint")
        take_btn = QPushButton("Převzít podmínky z aktuálního filtru")
        take_btn.clicked.connect(self._take_conditions)
        cond_box = QVBoxLayout()
        cond_box.addWidget(self.summary_label)
        cond_box.addWidget(take_btn)
        cond_group = QGroupBox("Podmínky filtrování")
        cond_group.setLayout(cond_box)

        self.editor = QGroupBox("Detail filtru")
        ed = QVBoxLayout(self.editor)
        ed.addLayout(form)
        ed.addWidget(cond_group)
        ed.addStretch(1)

        top = QHBoxLayout()
        lw = QWidget()
        lw.setLayout(left)
        lw.setMaximumWidth(240)
        top.addWidget(lw)
        top.addWidget(self.editor, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(top, 1)
        layout.addWidget(buttons)

        self._refresh_list()
        if self.working:
            self.list.setCurrentRow(0)
        else:
            self._set_editor_enabled(False)

    # ------------------------------------------------------------------
    def _refresh_list(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for sf in self.working:
            label = sf.name + (f"   [{sf.shortcut}]" if sf.shortcut else "")
            self.list.addItem(label)
        self.list.blockSignals(False)

    def _set_editor_enabled(self, on: bool) -> None:
        self.editor.setEnabled(on)

    def _on_row_changed(self, row: int) -> None:
        self._commit_editor()
        if 0 <= row < len(self.working):
            self._current = self.working[row]
            self._load_editor(self._current)
            self._set_editor_enabled(True)
        else:
            self._current = None
            self._set_editor_enabled(False)

    def _load_editor(self, sf: SavedFilter) -> None:
        for w in (self.name_edit, self.view_combo, self.sort_combo, self.dir_combo, self.key_edit):
            w.blockSignals(True)
        self.name_edit.setText(sf.name)
        self.view_combo.setCurrentIndex(self.view_combo.findData(sf.view))
        i = self.sort_combo.findData(sf.sort_key)
        self.sort_combo.setCurrentIndex(i if i >= 0 else 0)
        self.dir_combo.setCurrentIndex(1 if sf.sort_desc else 0)
        self.key_edit.setKeySequence(QKeySequence(sf.shortcut))
        for w in (self.name_edit, self.view_combo, self.sort_combo, self.dir_combo, self.key_edit):
            w.blockSignals(False)
        self.summary_label.setText(summary(sf))

    def _commit_editor(self) -> None:
        if self._current is None:
            return
        self._current.name = self.name_edit.text().strip() or "Filtr"
        self._current.view = self.view_combo.currentData()
        self._current.sort_key = self.sort_combo.currentData()
        self._current.sort_desc = bool(self.dir_combo.currentData())
        self._current.shortcut = self.key_edit.keySequence().toString(
            QKeySequence.SequenceFormat.PortableText
        )

    def _on_name_changed(self, text: str) -> None:
        row = self.list.currentRow()
        if self._current is not None and 0 <= row < self.list.count():
            self._current.name = text.strip() or "Filtr"
            sc = self.key_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
            self.list.item(row).setText(self._current.name + (f"   [{sc}]" if sc else ""))

    def _new_from_current(self) -> None:
        self._commit_editor()
        name, ok = QInputDialog.getText(self, "Nový filtr", "Název filtru:")
        if not ok or not name.strip():
            return
        sf = SavedFilter.from_preset(name.strip(), self.current_preset, self.current_view)
        self.working.append(sf)
        self._refresh_list()
        self.list.setCurrentRow(len(self.working) - 1)

    def _delete(self) -> None:
        row = self.list.currentRow()
        if 0 <= row < len(self.working):
            del self.working[row]
            self._current = None
            self._refresh_list()
            if self.working:
                self.list.setCurrentRow(min(row, len(self.working) - 1))
            else:
                self._set_editor_enabled(False)

    def _take_conditions(self) -> None:
        if self._current is None:
            return
        p = self.current_preset
        self._current.name_text = p.get("name", "")
        self._current.statuses = list(p.get("statuses", []) or [])
        self._current.priority_min = int(p.get("priority_min", 1) or 1)
        self._current.priority_max = int(p.get("priority_max", 10) or 10)
        self._current.categories = list(p.get("categories", []) or [])
        self._current.tags = list(p.get("tags", []) or [])
        self._current.flag = p.get("flag", None)
        self.summary_label.setText(summary(self._current))

    def _save(self) -> None:
        self._commit_editor()
        # kontrola kolizí zkratek
        used: dict[str, str] = {}
        for sf in self.working:
            if not sf.shortcut:
                continue
            if sf.shortcut in self.reserved:
                if not self._confirm_conflict(sf.shortcut, "vestavěným příkazem"):
                    return
            if sf.shortcut in used:
                if not self._confirm_conflict(sf.shortcut, f"filtrem „{used[sf.shortcut]}“"):
                    return
            used[sf.shortcut] = sf.name
        self.store.filters = self.working
        self.store.save()
        self.accept()

    def _confirm_conflict(self, seq: str, who: str) -> bool:
        ans = QMessageBox.question(
            self, "Kolize zkratek",
            f"Zkratka „{seq}“ koliduje s {who}. Uložit i tak?",
        )
        return ans == QMessageBox.StandardButton.Yes
