"""Panel filtrů.

Defaultně zobrazuje jen combo pro výběr uloženého filtru; kritéria
(stav, priorita, kategorie, tag, řazení) se zobrazí po rozkliknutí.
Výčtové vlastnosti lze zaškrtnout pro víc hodnot, priorita je rozmezí.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .constants import PRIORITIES, SORT_OPTIONS, STATUSES
from . import theme
from .widgets import SectionLabel

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
        # Zaškrtnuté hodnoty se cachují: filtr se vyhodnocuje pro KAŽDÝ úkol
        # a čtení stavu položek z Qt modelu bylo při stovkách úkolů většinou
        # času přebudování. Cache se zneplatní signály modelu – ty projdou
        # i při blockSignals() na comboboxu (apply_preset, reset).
        self._checked_cache: list | None = None
        for sig in (self._model.itemChanged, self._model.rowsInserted,
                    self._model.rowsRemoved, self._model.modelReset):
            sig.connect(self._invalidate_checked)

    def _invalidate_checked(self, *_) -> None:
        self._checked_cache = None

    def eventFilter(self, obj, event):
        if obj is self.view().viewport() and event.type() == QEvent.Type.MouseButtonRelease:
            idx = self.view().indexAt(event.position().toPoint())
            if idx.isValid():
                item = self._model.itemFromIndex(idx)
                checked = item.checkState() == Qt.CheckState.Checked
                item.setCheckState(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)
                self._update_text()
                self.changed.emit()
            return True
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
        if self._checked_cache is None:
            self._checked_cache = [
                it.data(DATA_ROLE)
                for it in (self._model.item(i) for i in range(self._model.rowCount()))
                if it.checkState() == Qt.CheckState.Checked
            ]
        return list(self._checked_cache)  # kopie – volající si ji smí upravit

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
    sortChanged = Signal(str, bool, str, bool)
    savedFilterSelected = Signal(str)  # id uloženého filtru ("" = žádný)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._applying = False

        # --- výběr uloženého filtru + rozbalení kritérií ---
        self.saved_combo = QComboBox()
        self.saved_combo.addItem("— uložený filtr —", "")
        self.expand_btn = QToolButton()
        self.expand_btn.setCheckable(True)
        self.expand_btn.setAutoRaise(True)
        self.expand_btn.setText("Kritéria ▸")
        self.expand_btn.setToolTip("Zobrazit/skrýt kritéria filtru")
        self.expand_btn.toggled.connect(self._toggle_criteria)

        # --- kritéria ---
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("hledat v názvu…")
        self.name_edit.setClearButtonEnabled(True)

        self.status_box = CheckableComboBox()
        for key, label in STATUSES.items():
            self.status_box.add_value(label, key)
        self.category_box = CheckableComboBox()
        self.tag_box = CheckableComboBox()

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

        self.flag_combo = QComboBox()
        self.flag_combo.addItem("— vlaječka —", None)
        self.flag_combo.addItem("🚩 jen označené", True)
        self.flag_combo.addItem("bez vlaječky", False)

        self.sort_combo = QComboBox()
        for key, label in SORT_OPTIONS.items():
            self.sort_combo.addItem(label, key)
        self.sort_dir_combo = QComboBox()
        self.sort_dir_combo.addItem("Vzestupně ↑", False)
        self.sort_dir_combo.addItem("Sestupně ↓", True)

        # name_edit (hledání v názvu) stojí v hlavičce okna – hlavní okno si ho
        # z panelu vezme; zůstává ale kritériem filtru (current_filters)
        form = QFormLayout()
        form.addRow("Stav:", self.status_box)
        form.addRow("Priorita:", prio_widget)
        form.addRow("Kategorie:", self.category_box)
        form.addRow("Tag:", self.tag_box)
        form.addRow("Vlaječka:", self.flag_combo)
        form.addRow("Řadit dle:", self.sort_combo)
        form.addRow("Směr:", self.sort_dir_combo)

        self.reset_btn = QPushButton("Zrušit filtry")
        self.reset_btn.setProperty("quiet", "true")
        self.reset_btn.clicked.connect(self.reset)

        self.criteria = QWidget()
        crit_layout = QVBoxLayout(self.criteria)
        self._crit_layout = crit_layout
        crit_layout.addLayout(form)
        reset_row = QHBoxLayout()
        reset_row.addStretch(1)
        reset_row.addWidget(self.reset_btn)
        crit_layout.addLayout(reset_row)
        self.criteria.setVisible(False)

        # hlavička sekce: FILTRY … Kritéria ▸ ; pod ní uložený filtr přes celou šířku
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(SectionLabel("Filtry"))
        head.addStretch(1)
        head.addWidget(self.expand_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._layout = layout
        layout.addLayout(head)
        layout.addWidget(self.saved_combo)
        layout.addWidget(self.criteria)
        self.retheme()

        # signály kritérií
        self.name_edit.textChanged.connect(self._criteria_changed)
        self.status_box.changed.connect(self._criteria_changed)
        self.category_box.changed.connect(self._criteria_changed)
        self.tag_box.changed.connect(self._criteria_changed)
        self.flag_combo.currentIndexChanged.connect(self._criteria_changed)
        self.prio_min.valueChanged.connect(self._on_prio_changed)
        self.prio_max.valueChanged.connect(self._on_prio_changed)

        # řazení (zvlášť kvůli reseedu vlastního pořadí)
        self._cur_sort = self.current_sort()
        self.sort_combo.currentIndexChanged.connect(self._on_sort_ui_changed)
        self.sort_dir_combo.currentIndexChanged.connect(self._on_sort_ui_changed)

        # výběr uloženého filtru
        self.saved_combo.currentIndexChanged.connect(self._on_saved_selected)

    # ------------------------------------------------------------------
    def retheme(self) -> None:
        """Mezery panelu podle zoomu."""
        self._crit_layout.setContentsMargins(0, theme.px(4), 0, 0)
        self._layout.setSpacing(theme.px(6))

    def _toggle_criteria(self, on: bool) -> None:
        self.criteria.setVisible(on)
        self.expand_btn.setText("Kritéria ▾" if on else "Kritéria ▸")

    def _criteria_changed(self) -> None:
        if self._applying:
            return
        self._set_saved_silent("")  # ruční změna -> „vlastní"
        self.filtersChanged.emit()

    def _on_prio_changed(self) -> None:
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
        self._criteria_changed()

    def _on_sort_ui_changed(self) -> None:
        new = self.current_sort()
        prev = self._cur_sort
        if new == prev:
            return
        self._cur_sort = new
        if not self._applying:
            self._set_saved_silent("")
        self.sortChanged.emit(prev[0], prev[1], new[0], new[1])

    # ----- uložené filtry v combu -----
    def populate_saved(self, items) -> None:
        """items: seznam (id, name). Zachová aktuální výběr podle id."""
        current = self.saved_combo.currentData()
        self.saved_combo.blockSignals(True)
        self.saved_combo.clear()
        self.saved_combo.addItem("— uložený filtr —", "")
        for fid, name in items:
            self.saved_combo.addItem(name, fid)
        idx = self.saved_combo.findData(current)
        self.saved_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.saved_combo.blockSignals(False)

    def set_saved(self, filter_id: str) -> None:
        self._set_saved_silent(filter_id or "")

    def _set_saved_silent(self, filter_id: str) -> None:
        idx = self.saved_combo.findData(filter_id)
        if idx < 0:
            idx = 0
        if self.saved_combo.currentIndex() != idx:
            self.saved_combo.blockSignals(True)
            self.saved_combo.setCurrentIndex(idx)
            self.saved_combo.blockSignals(False)

    def _on_saved_selected(self) -> None:
        if self._applying:
            return
        fid = self.saved_combo.currentData() or ""
        if fid:
            self.savedFilterSelected.emit(fid)

    # ------------------------------------------------------------------
    def populate_dynamic(self, categories: list[str], tags: list[str]) -> None:
        for box, values in ((self.category_box, categories), (self.tag_box, tags)):
            checked = set(box.checked_data())
            box.blockSignals(True)
            box.clear_values()
            for v in values:
                box.add_value(v, v)
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
        self.flag_combo.setCurrentIndex(0)
        self.blockSignals(False)
        self._set_saved_silent("")
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
            "flag": self.flag_combo.currentData(),
        }

    @staticmethod
    def _status_matches(node, wanted) -> bool:
        """Vyhovuje stav úkolu filtru?

        Doběhlý odklad si technicky drží stav „snoozed" (kvůli tlačítku
        Obnovit), ale už nečeká – volá po akci. Nesmí tedy zmizet z pohledu
        jen proto, že uživatel filtruje na aktivní stavy; bere se jako „todo".
        """
        status = node.meta.get("_status")
        if status == "snoozed" and node.snooze_elapsed():
            return "todo" in wanted or "snoozed" in wanted
        return status in wanted

    def matcher(self):
        """Funkce úkol -> bool s JEDNOU sejmutým filtrem.

        Pro průchody přes všechny úkoly (přebudování zobrazení, zařazení
        nového úkolu): matches() by jinak četl stav widgetů pro každý úkol
        znovu a čas rostl s celkovým počtem úkolů, ne s počtem viditelných.
        """
        f = self.current_filters()
        return lambda node: self.matches(node, f)

    def matches(self, node, filters: dict | None = None) -> bool:
        f = filters if filters is not None else self.current_filters()
        meta = node.meta
        if f["name"] and f["name"] not in node.title.lower():
            return False
        if f["statuses"] and not self._status_matches(node, f["statuses"]):
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
        if f["flag"] is not None and bool(meta.get("_flag", False)) != f["flag"]:
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

    # ----- presety -----
    def export_preset(self) -> dict:
        f = self.current_filters()
        f["name"] = self.name_edit.text().strip()
        key, desc = self.current_sort()
        f["sort_key"] = key
        f["sort_desc"] = desc
        return f

    def apply_preset(self, data: dict) -> None:
        self._applying = True
        self.blockSignals(True)
        self.name_edit.setText(data.get("name", "") or "")
        self.status_box.set_checked_data(data.get("statuses", []) or [])
        self.prio_min.setValue(int(data.get("priority_min", 1) or 1))
        self.prio_max.setValue(int(data.get("priority_max", 10) or 10))
        flag_val = data.get("flag", None)
        self.flag_combo.setCurrentIndex(self.flag_combo.findData(flag_val) if flag_val is not None else 0)
        for box, key in ((self.category_box, "categories"), (self.tag_box, "tags")):
            vals = data.get(key, []) or []
            existing = {box._model.item(i).data(DATA_ROLE) for i in range(box._model.rowCount())}
            for v in vals:
                if v not in existing:
                    box.add_value(v, v)
            box.set_checked_data(vals)
        self.set_sort(data.get("sort_key", "title"), bool(data.get("sort_desc", False)))
        self.blockSignals(False)
        self._applying = False
