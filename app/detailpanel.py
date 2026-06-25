"""Pravý panel s detailem úkolu: metadata, WYSIWYG editor a odkazy na soubory."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .constants import PRIORITIES, STATUSES
from .editor import MarkdownEditor
from .storage import TaskNode

PATH_ROLE = Qt.ItemDataRole.UserRole
REF_ROLE = Qt.ItemDataRole.UserRole


def _icon_btn(text: str, tooltip: str, slot) -> "QPushButton":
    b = QPushButton(text)
    b.setToolTip(tooltip)
    b.setFixedWidth(34)
    b.clicked.connect(slot)
    return b


class LinkList(QListWidget):
    """Seznam odkazů, který umí přijmout přetažené soubory."""

    filesDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            if paths:
                self.filesDropped.emit(paths)
            event.acceptProposedAction()


class TaskDetailPanel(QWidget):
    metaChanged = Signal(object)   # TaskNode (titulek/stav/... se změnil)
    navigateTo = Signal(object)    # TaskNode – přejít na související úkol
    addRefRequested = Signal()     # uživatel chce přidat odkaz na úkol

    def __init__(self, parent=None):
        super().__init__(parent)
        self.node: TaskNode | None = None
        self._loading = False
        # funkce id -> TaskNode pro překlad odkazů (nastaví hlavní okno)
        self.resolver = None

        # --- metadata (kompaktní mřížka, 2 sloupce) ---
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("název úkolu")
        # vlaječka jako klikací ikona (vyplněná = zapnuto)
        self.flag_btn = QToolButton()
        self.flag_btn.setCheckable(True)
        self.flag_btn.setAutoRaise(True)
        self.flag_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.flag_btn.setToolTip("Vlaječka (Ctrl+T)")
        self.flag_btn.setText("⚐")
        self.flag_btn.setStyleSheet(
            "QToolButton{border:none;font-size:20px;color:#b8b8b8;padding:0 2px;}"
            "QToolButton:checked{color:#e23b3b;}"
        )
        self.flag_btn.toggled.connect(self._on_flag_btn)

        self.status_combo = QComboBox()
        for k, v in STATUSES.items():
            self.status_combo.addItem(v, k)
        self.priority_combo = QComboBox()
        for k, v in PRIORITIES.items():
            self.priority_combo.addItem(v, k)
        self.category_edit = QLineEdit()
        self.category_edit.setPlaceholderText("kategorie")
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("tagy oddělené čárkou")
        self.path_label = QLabel("—")
        self.path_label.setStyleSheet("color:#999; font-size:10px;")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        def _lbl(text):
            la = QLabel(text)
            la.setStyleSheet("color:#666;")
            return la

        grid = QGridLayout()
        grid.setContentsMargins(8, 4, 8, 4)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)
        grid.addWidget(self.title_edit, 0, 0, 1, 3)
        grid.addWidget(self.flag_btn, 0, 3, Qt.AlignmentFlag.AlignRight)
        grid.addWidget(_lbl("Stav"), 1, 0)
        grid.addWidget(self.status_combo, 1, 1)
        grid.addWidget(_lbl("Priorita"), 1, 2)
        grid.addWidget(self.priority_combo, 1, 3)
        grid.addWidget(_lbl("Kategorie"), 2, 0)
        grid.addWidget(self.category_edit, 2, 1)
        grid.addWidget(_lbl("Tagy"), 2, 2)
        grid.addWidget(self.tags_edit, 2, 3)
        grid.addWidget(self.path_label, 3, 0, 1, 4)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        meta_box = QGroupBox("Metadata")
        meta_box.setLayout(grid)

        # --- editor ---
        self.editor = MarkdownEditor()
        self.editor.setMinimumWidth(160)
        editor_box = QGroupBox("Popis")
        eb = QVBoxLayout(editor_box)
        eb.setContentsMargins(4, 4, 4, 4)
        eb.addWidget(self.editor)

        # --- odkazy na soubory ---
        self.link_list = LinkList()
        self.link_list.setMinimumWidth(80)
        self.link_list.itemDoubleClicked.connect(lambda _: self._open_link())
        open_btn = _icon_btn("📂", "Otevřít soubor", self._open_link)
        folder_btn = _icon_btn("🗁", "Otevřít složku", self._open_folder)
        remove_btn = _icon_btn("✕", "Odebrat odkaz", self._remove_link)
        self.link_list.filesDropped.connect(self._on_files_dropped)
        link_btns = QHBoxLayout()
        link_btns.addWidget(open_btn)
        link_btns.addWidget(folder_btn)
        link_btns.addWidget(remove_btn)
        link_btns.addStretch(1)
        links_box = QGroupBox("Soubory 📎")
        links_box.setToolTip("Odkazy na soubory – přetáhni sem soubory")
        lb = QVBoxLayout(links_box)
        lb.addWidget(self.link_list)
        lb.addLayout(link_btns)

        # --- odkazy na jiné úkoly ---
        self.ref_list = QListWidget()
        self.ref_list.setMinimumWidth(80)
        self.ref_list.itemDoubleClicked.connect(lambda _: self._goto_ref())
        add_ref_btn = _icon_btn("＋", "Přidat odkaz na úkol", lambda: self.addRefRequested.emit())
        goto_ref_btn = _icon_btn("➜", "Přejít na úkol", self._goto_ref)
        rm_ref_btn = _icon_btn("✕", "Odebrat odkaz", self._remove_ref)
        ref_btns = QHBoxLayout()
        ref_btns.addWidget(add_ref_btn)
        ref_btns.addWidget(goto_ref_btn)
        ref_btns.addWidget(rm_ref_btn)
        ref_btns.addStretch(1)
        refs_box = QGroupBox("Úkoly 🔗")
        rb = QVBoxLayout(refs_box)
        rb.addWidget(self.ref_list)
        rb.addLayout(ref_btns)

        # spodní pás: soubory | úkoly vedle sebe
        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.addWidget(links_box)
        bottom_splitter.addWidget(refs_box)
        bottom_splitter.setStretchFactor(0, 1)
        bottom_splitter.setStretchFactor(1, 1)

        # --- rozložení ---
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(editor_box)
        splitter.addWidget(bottom_splitter)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(meta_box)
        layout.addWidget(splitter, 1)

        # --- signály ---
        self.title_edit.editingFinished.connect(self._apply_title)
        self.status_combo.currentIndexChanged.connect(lambda: self._apply_field("_status", self.status_combo.currentData()))
        self.priority_combo.currentIndexChanged.connect(lambda: self._apply_field("_priority", self.priority_combo.currentData()))
        self.category_edit.editingFinished.connect(lambda: self._apply_field("_category", self.category_edit.text().strip()))
        self.tags_edit.editingFinished.connect(self._apply_tags)

        # autosave těla po krátké pauze v psaní
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1200)
        self._save_timer.timeout.connect(self._save_body)
        self.editor.contentChanged.connect(self._on_editor_changed)

        self.setEnabled(False)

    # ------------------------------------------------------------------
    # Načtení / uložení
    # ------------------------------------------------------------------
    def load(self, node: TaskNode | None) -> None:
        self.commit()  # ulož předchozí
        self.node = node
        if node is None:
            self._loading = True
            self.title_edit.clear()
            self.category_edit.clear()
            self.tags_edit.clear()
            self.editor.clear()
            self.link_list.clear()
            self.ref_list.clear()
            self.flag_btn.setChecked(False)
            self.path_label.setText("—")
            self.setEnabled(False)
            self._loading = False
            return

        self._loading = True
        self.setEnabled(True)
        self.title_edit.setText(node.title)
        self._select_data(self.status_combo, node.meta.get("_status"))
        self._select_data(self.priority_combo, node.meta.get("_priority"))
        self.category_edit.setText(node.meta.get("_category", "") or "")
        self.tags_edit.setText(", ".join(node.meta.get("_tags", []) or []))
        self.flag_btn.setChecked(bool(node.meta.get("_flag", False)))
        self.path_label.setText(node.path.as_posix())
        self.editor.set_markdown(node.read_body())
        self._refresh_links()
        self._refresh_refs()
        self._loading = False

    def commit(self) -> None:
        """Uloží rozpracované tělo na disk (metadata se ukládají průběžně)."""
        if self.node is None:
            return
        self._save_timer.stop()
        self._save_body()

    def discard(self) -> None:
        """Odpojí aktuální úkol BEZ ukládání (před strukturální změnou)."""
        self._save_timer.stop()
        self.node = None

    def _save_body(self) -> None:
        if self.node is None:
            return
        self.node.write_body(self.editor.to_markdown())

    def _on_editor_changed(self) -> None:
        if not self._loading and self.node is not None:
            self._save_timer.start()

    # ------------------------------------------------------------------
    # Aplikace metadat
    # ------------------------------------------------------------------
    def _apply_field(self, key: str, value) -> None:
        if self._loading or self.node is None:
            return
        self.node.set_field(key, value)
        self.metaChanged.emit(self.node)

    def _apply_title(self) -> None:
        if self._loading or self.node is None:
            return
        text = self.title_edit.text().strip() or self.node.name
        if text != self.node.meta.get("_title"):
            self.node.set_field("_title", text)
            self.metaChanged.emit(self.node)

    def _apply_tags(self) -> None:
        if self._loading or self.node is None:
            return
        tags = [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]
        self.node.set_field("_tags", tags)
        self.metaChanged.emit(self.node)

    def _select_data(self, combo: QComboBox, data) -> None:
        idx = combo.findData(data)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def sync_status(self, status: str) -> None:
        """Promítne stav nastavený zvenčí (checkbox ve stromu) do comboboxu."""
        if self.node is None:
            return
        self._loading = True
        self._select_data(self.status_combo, status)
        self._loading = False

    def sync_priority(self, priority) -> None:
        if self.node is None:
            return
        self._loading = True
        self._select_data(self.priority_combo, priority)
        self._loading = False

    def sync_flag(self, state: bool) -> None:
        if self.node is None:
            return
        self._loading = True
        self.flag_btn.setChecked(bool(state))
        self._loading = False

    def _on_flag_btn(self, checked: bool) -> None:
        self.flag_btn.setText("⚑" if checked else "⚐")
        self._apply_field("_flag", bool(checked))

    # ------------------------------------------------------------------
    # Odkazy
    # ------------------------------------------------------------------
    def _refresh_links(self) -> None:
        self.link_list.clear()
        if self.node is None:
            return
        for link in self.node.links:
            path = link.get("path", "")
            exists = os.path.exists(path)
            item = QListWidgetItem(("" if exists else "⚠ ") + link.get("name", path))
            item.setToolTip(path + ("" if exists else "\n(soubor nenalezen)"))
            item.setData(PATH_ROLE, path)
            self.link_list.addItem(item)

    def _on_files_dropped(self, paths: list) -> None:
        if self.node is None:
            return
        changed = False
        for p in paths:
            if self.node.add_link(p):
                changed = True
        if changed:
            self._refresh_links()
            self.metaChanged.emit(self.node)

    def add_links(self, paths: list) -> None:
        self._on_files_dropped(paths)

    def _current_link_path(self) -> str | None:
        item = self.link_list.currentItem()
        return item.data(PATH_ROLE) if item else None

    def _open_link(self) -> None:
        path = self._current_link_path()
        if path and os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _open_folder(self) -> None:
        path = self._current_link_path()
        if path:
            folder = str(Path(path).parent)
            if os.path.exists(folder):
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _remove_link(self) -> None:
        if self.node is None:
            return
        row = self.link_list.currentRow()
        if row >= 0:
            self.node.remove_link(row)
            self._refresh_links()
            self.metaChanged.emit(self.node)

    def refresh_links_external(self) -> None:
        self._refresh_links()

    # ------------------------------------------------------------------
    # Odkazy na jiné úkoly
    # ------------------------------------------------------------------
    def _refresh_refs(self) -> None:
        self.ref_list.clear()
        if self.node is None:
            return
        for rid in self.node.refs:
            target = self.resolver(rid) if self.resolver else None
            title = target.title if target is not None else "(smazaný úkol)"
            item = QListWidgetItem("↪ " + title)
            item.setData(REF_ROLE, rid)
            if target is not None:
                item.setToolTip(target.path.as_posix())
            else:
                item.setForeground(Qt.GlobalColor.gray)
            self.ref_list.addItem(item)

    def refresh_refs(self) -> None:
        self._refresh_refs()

    def _current_ref_id(self) -> str | None:
        item = self.ref_list.currentItem()
        return item.data(REF_ROLE) if item else None

    def _goto_ref(self) -> None:
        rid = self._current_ref_id()
        if not rid or self.resolver is None:
            return
        target = self.resolver(rid)
        if target is not None:
            self.navigateTo.emit(target)

    def _remove_ref(self) -> None:
        if self.node is None:
            return
        rid = self._current_ref_id()
        if rid:
            self.node.remove_ref(rid)
            self._refresh_refs()
            self.metaChanged.emit(self.node)
