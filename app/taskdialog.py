"""Dialogy: nový/upravený úkol s metadaty a volba pozice při vkládání."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from .constants import DEFAULT_PRIORITY, DEFAULT_STATUS, PRIORITIES, STATUSES


class TaskDialog(QDialog):
    """Dialog pro zadání úkolu i s metadaty."""

    def __init__(self, window_title="Nový úkol", defaults=None, parent=None):
        super().__init__(parent)
        defaults = defaults or {}
        self.setWindowTitle(window_title)
        self.setMinimumWidth(360)

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

        form = QFormLayout()
        form.addRow("Název:", self.title_edit)
        form.addRow("Stav:", self.status_combo)
        form.addRow("Priorita:", self.priority_combo)
        form.addRow("Kategorie:", self.category_edit)
        form.addRow("Tagy:", self.tags_edit)
        form.addRow("", self.flag_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.title_edit.setFocus()

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
        }

    @staticmethod
    def get(parent, window_title, defaults=None) -> dict | None:
        dlg = TaskDialog(window_title, defaults, parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vals = dlg.values()
            if vals["title"]:
                return vals
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
