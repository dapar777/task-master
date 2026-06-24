"""Panel filtrů: hledání podle názvu, stavu, kategorie, priority a tagu.

Výčtové vlastnosti (stav, kategorie, tag) lze zaškrtnout pro VÍCE hodnot.
Priorita se filtruje rozmezím od–do.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .constants import PRIORITIES, SORT_OPTIONS, STATUSES

DATA_ROLE = Qt.ItemDataRole.UserRole


class CheckableComboBox(QComboBox):
    """ComboBox, kde lze zaškrtnout více položek; popup zůstává otevřený."""

    changed = Signal()

    def __init__(self, placeholder="— vše —", parent=None):
        super().__init__(parent)
        self._placeholder = placeholder
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText(placeholder)
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        self.view().viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.view().viewport() and event.type() == QEvent.Type.MouseButtonRelease:
            idx = self.view().indexAt(event.position().toPoint())
            if idx.isValid():
                item = self._model.itemFromIndex(idx)
                checked = item.checkState() == Qt.CheckState.Checked
                item.setCheckState(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)
                self._update_text()
                self.changed.emit()
            return True  # nezavírat popup
        return super().eventFilter(obj, event)

    def add_value(self, label: str, data) -> None:
        item = QStandardItem(label)
        item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        item.setData(Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
        item.setData(data, DATA_ROLE)
        self._model.appendRow(item)

    def clear_values(self) -> None:
        self._model.clear()

    def checked_data(self) -> list:
        out = []
        for i in range(self._model.rowCount()):
            it = self._model.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                out.append(it.data(DATA_ROLE))
        return out

    def set_checked_data(self, values) -> None:
        vals = set(values or [])
        for i in range(self._model.rowCount()):
            it = self._model.item(i)
            on = it.data(DATA_ROLE) in vals
            it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        self._update_text()

    def _update_text(self) -> None:
        labels = [
            self._model.item(i).text()
            for i in range(self._model.rowCount())
            if self._model.item(i).checkState() == Qt.CheckState.Checked
        ]
        self.lineEdit().setText(", ".join(labels))


class FilterPanel(QWidget):
    filtersChanged = Signal()
    sortChanged = Signal(str, bool, str, bool)  # prev_key, prev_desc, new_key, new_desc

    def __init__(self, parent=None):
        super().__init__(parent)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("hledat v názvu…")
        self.name_edit.setClearButtonEnabled(True)

        self.status_box = CheckableComboBox()
        for key, label in STATUSES.items():
            self.status_box.add_value(label, key)

        self.category_box = CheckableComboBox()
        self.tag_box = CheckableComboBox()

        # priorita jako rozmezí od–do
        self.prio_min = QSpinBox()
        self.prio_min.setRange(1, 10)
        self.prio_min.setValue(1)
        self.prio_max = QSpinBox()
        self.prio_max.setRange(1, 10)
        self.prio_max.setValue(10)
        prio_row = QHBoxLayout()
        prio_row.setContentsMargins(0, 0, 0, 0)
        prio_row.addWidget(QLabel("od"))
        prio_row.addWidget(self.prio_min)
        prio_row.addWidget(QLabel("do"))
        prio_row.addWidget(self.prio_max)
        prio_row.addStretch(1)
        prio_widget = QWidget()
        prio_widget.setLayout(prio_row)

        # řazení
        self.sort_combo = QComboBox()
        for key, label in SORT_OPTIONS.items():
            self.sort_combo.addItem(label, key)
        self.sort_dir_combo = QComboBox()
        self.sort_dir_combo.addItem("Vzestupně ↑", False)
        self.sort_dir_combo.addItem("Sestupně ↓", True)

        form = QFormLayout()
        form.addRow("Název:", self.name_edit)
        form.addRow("Stav:", self.status_box)
        form.addRow("Priorita:", prio_widget)
        form.addRow("Kategorie:", self.category_box)
        form.addRow("Tag:", self.tag_box)
        form.addRow("Řadit dle:", self.sort_combo)
        form.addRow("Směr:", self.sort_dir_combo)

        self.reset_btn = QPushButton("Zrušit filtry")
        self.reset_btn.clicked.connect(self.reset)

        box = QGroupBox("Filtry")
        box_layout = QVBoxLayout(box)
        box_layout.addLayout(form)
        box_layout.addWidget(self.reset_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(box)

        # signály filtrů
        self.name_edit.textChanged.connect(self.filtersChanged)
        self.status_box.changed.connect(self.filtersChanged)
        self.category_box.changed.connect(self.filtersChanged)
        self.tag_box.changed.connect(self.filtersChanged)
        self.prio_min.valueChanged.connect(self._on_prio_changed)
        self.prio_max.valueChanged.connect(self._on_prio_changed)

        # signály řazení (zvlášť kvůli reseedu vlastního pořadí)
        self._cur_sort = self.current_sort()
        self.sort_combo.currentIndexChanged.connect(self._on_sort_ui_changed)
        self.sort_dir_combo.currentIndexChanged.connect(self._on_sort_ui_changed)

    # ------------------------------------------------------------------
    def _on_prio_changed(self) -> None:
        # udrž min <= max
        if self.prio_min.value() > self.prio_max.value():
            sender = self.sender()
            if sender is self.prio_min:
                self.prio_max.blockSignals(True)
                self.prio_max.setValue(self.prio_min.value())
                self.prio_max.blockSignals(False)
            else:
                self.prio_min.blockSignals(True)
                self.prio_min.setValue(self.prio_max.value())
                self.prio_min.blockSignals(False)
        self.filtersChanged.emit()

    def _on_sort_ui_changed(self) -> None:
        new = self.current_sort()
        prev = self._cur_sort
        if new == prev:
            return
        self._cur_sort = new
        self.sortChanged.emit(prev[0], prev[1], new[0], new[1])

    # ------------------------------------------------------------------
    def populate_dynamic(self, categories: list[str], tags: list[str]) -> None:
        for box, values in ((self.category_box, categories), (self.tag_box, tags)):
            checked = set(box.checked_data())
            box.blockSignals(True)
            box.clear_values()
            for v in values:
                box.add_value(v, v)
            # zachovej i hodnoty, které zrovna v datech nejsou (z presetu)
            for v in checked:
                if v not in values:
                    box.add_value(v, v)
            box.set_checked_data(checked)
            box.blockSignals(False)

    def reset(self) -> None:
        self.blockSignals(True)
        self.name_edit.clear()
        self.status_box.set_checked_data([])
        self.category_box.set_checked_data([])
        self.tag_box.set_checked_data([])
        self.prio_min.setValue(1)
        self.prio_max.setValue(10)
        self.blockSignals(False)
        self.filtersChanged.emit()

    # ------------------------------------------------------------------
    def current_filters(self) -> dict:
        return {
            "name": self.name_edit.text().strip().lower(),
            "statuses": self.status_box.checked_data(),
            "priority_min": self.prio_min.value(),
            "priority_max": self.prio_max.value(),
            "categories": self.category_box.checked_data(),
            "tags": self.tag_box.checked_data(),
        }

    def matches(self, node) -> bool:
        f = self.current_filters()
        meta = node.meta
        if f["name"] and f["name"] not in node.title.lower():
            return False
        if f["statuses"] and meta.get("_status") not in f["statuses"]:
            return False
        try:
            p = int(meta.get("_priority", 5))
        except (TypeError, ValueError):
            p = 5
        if not (f["priority_min"] <= p <= f["priority_max"]):
            return False
        if f["categories"] and (meta.get("_category", "") or "") not in f["categories"]:
            return False
        if f["tags"]:
            node_tags = set(meta.get("_tags", []) or [])
            if not node_tags.intersection(f["tags"]):
                return False
        return True

    # ----- řazení -----
    def current_sort(self) -> tuple[str, bool]:
        return self.sort_combo.currentData() or "title", bool(self.sort_dir_combo.currentData())

    def set_sort(self, key: str, desc: bool) -> None:
        self.blockSignals(True)
        i = self.sort_combo.findData(key)
        self.sort_combo.setCurrentIndex(i if i >= 0 else 0)
        self.sort_dir_combo.setCurrentIndex(1 if desc else 0)
        self.blockSignals(False)
        self._cur_sort = self.current_sort()

    # ----- uložené filtry (presety) -----
    def export_preset(self) -> dict:
        f = self.current_filters()
        f["name"] = self.name_edit.text().strip()
        key, desc = self.current_sort()
        f["sort_key"] = key
        f["sort_desc"] = desc
        return f

    def apply_preset(self, data: dict) -> None:
        self.blockSignals(True)
        self.name_edit.setText(data.get("name", "") or "")
        self.status_box.set_checked_data(data.get("statuses", []) or [])
        self.prio_min.setValue(int(data.get("priority_min", 1) or 1))
        self.prio_max.setValue(int(data.get("priority_max", 10) or 10))
        # u kategorie/tagu doplň chybějící hodnoty, ať je lze zaškrtnout
        for box, key in ((self.category_box, "categories"), (self.tag_box, "tags")):
            vals = data.get(key, []) or []
            existing = {box._model.item(i).data(DATA_ROLE) for i in range(box._model.rowCount())}
            for v in vals:
                if v not in existing:
                    box.add_value(v, v)
            box.set_checked_data(vals)
        self.set_sort(data.get("sort_key", "title"), bool(data.get("sort_desc", False)))
        self.blockSignals(False)
