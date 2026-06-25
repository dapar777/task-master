"""Příkazová paleta (Ctrl+Shift+P) – vyhledávání a spouštění příkazů."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

ENTRY_ROLE = Qt.ItemDataRole.UserRole


class CommandPalette(QDialog):
    """entries: list slovníků {label, category, shortcut, run(callable)}."""

    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self._entries = entries
        self.setWindowTitle("Příkazy")
        self.setModal(True)
        self.resize(580, 440)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Hledat příkaz…")
        self.search.setClearButtonEnabled(True)
        self.list = QListWidget()
        self.list.setUniformItemSizes(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.search)
        layout.addWidget(self.list, 1)

        self.search.textChanged.connect(self._filter)
        self.list.itemActivated.connect(lambda _: self._run_current())
        self.search.installEventFilter(self)

        self._filter("")
        self.search.setFocus()

    # ------------------------------------------------------------------
    def _matches(self, e: dict, q: str) -> bool:
        if not q:
            return True
        hay = (e.get("category", "") + " " + e.get("label", "")).lower()
        # všechny tokeny musí být obsažené (jednoduché fuzzy)
        return all(tok in hay for tok in q.split())

    def _filter(self, q: str) -> None:
        q = q.strip().lower()
        self.list.clear()
        for e in self._entries:
            if not self._matches(e, q):
                continue
            label = e["label"]
            if e.get("category"):
                label = f"{e['category']}  ·  {label}"
            it = QListWidgetItem(label)
            sc = e.get("shortcut") or ""
            if sc:
                it.setToolTip(sc)
                it.setText(label + (f"      [{sc}]"))
            it.setData(ENTRY_ROLE, e)
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _run_current(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        entry = item.data(ENTRY_ROLE)
        self.accept()
        run = entry.get("run")
        if callable(run):
            run()

    # ------------------------------------------------------------------
    def eventFilter(self, obj, event):
        if obj is self.search and event.type() == event.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.list.currentRow()
                row += 1 if key == Qt.Key.Key_Down else -1
                row = max(0, min(self.list.count() - 1, row))
                self.list.setCurrentRow(row)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._run_current()
                return True
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        par = self.parent()
        if par is not None:
            geo = par.window().frameGeometry()
            self.move(geo.center().x() - self.width() // 2,
                      geo.center().y() - self.height() // 2)
