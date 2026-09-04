"""Pravý panel s detailem úkolu: hlavička (cesta, název, chipy), WYSIWYG editor a odkazy.

Hlavička nahrazuje dřívější groupbox „Metadata“: stejná pole (stav, priorita,
vlaječka, kategorie, tagy, cesta na disku), stejné okamžité ukládání.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import icons, theme
from .constants import PRIORITIES, STATUSES
from .editor import MarkdownEditor
from .storage import TaskNode
from .tasktree import breadcrumb
from .widgets import HLine, IconButton, SectionLabel

PATH_ROLE = Qt.ItemDataRole.UserRole
REF_ROLE = Qt.ItemDataRole.UserRole


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


class FlagButton(IconButton):
    """Přepínač vlaječky: obrys = vypnuto, vyplněná v akcentu = zapnuto."""

    def __init__(self, parent=None):
        super().__init__("flag_outline", "Vlaječka (Ctrl+T)", parent)
        self.setCheckable(True)
        self.toggled.connect(lambda _c: self.retheme())

    def retheme(self) -> None:
        t = theme.current()
        on = self.isChecked()
        self.setIcon(icons.icon("flag" if on else "flag_outline", 16, t.accent if on else t.muted))


def _section(title: str, hint: str, buttons: list[IconButton]) -> tuple[QWidget, QVBoxLayout]:
    """Sekce spodního pásu: nadpis, nápověda, ikonová tlačítka; obsah doplní volající."""
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(12, 8, 12, 8)
    v.setSpacing(4)
    head = QHBoxLayout()
    head.setSpacing(8)
    head.addWidget(SectionLabel(title))
    if hint:
        h = QLabel(hint)
        h.setObjectName("faintLabel")
        head.addWidget(h)
    head.addStretch(1)
    for b in buttons:
        head.addWidget(b)
    v.addLayout(head)
    return box, v


class TaskDetailPanel(QWidget):
    metaChanged = Signal(object)   # TaskNode (titulek/stav/... se změnil)
    statusChanged = Signal(object, str)  # (TaskNode, nový stav) – změna z comboboxu
    navigateTo = Signal(object)    # TaskNode – přejít na související úkol
    addRefRequested = Signal()     # uživatel chce přidat odkaz na úkol

    def __init__(self, parent=None):
        super().__init__(parent)
        self.node: TaskNode | None = None
        self._loading = False
        # funkce id -> TaskNode pro překlad odkazů (nastaví hlavní okno)
        self.resolver = None

        # --- hlavička úkolu: cesta, název s checkboxem, řádek chipů ---
        self.crumb_label = QLabel("—")
        self.crumb_label.setObjectName("pathLabel")
        self.crumb_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self.done_check = QCheckBox()
        self.done_check.setToolTip("Hotovo (Ctrl+Enter)")
        self.title_label = QLabel("—")
        self.title_label.setFont(theme.title_font(16))
        self.title_label.setWordWrap(True)
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_row.addWidget(self.done_check, 0, Qt.AlignmentFlag.AlignTop)
        title_row.addWidget(self.title_label, 1)

        self.flag_btn = FlagButton()
        self.status_combo = QComboBox()
        for k, v in STATUSES.items():
            self.status_combo.addItem(v, k)
        self.priority_combo = QComboBox()
        for k, v in PRIORITIES.items():
            self.priority_combo.addItem(f"P{v}", k)
        self.priority_combo.setToolTip("Priorita (Ctrl+↑ / Ctrl+↓)")
        self.category_edit = QLineEdit()
        self.category_edit.setPlaceholderText("kategorie")
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("tagy oddělené čárkou")
        self.path_label = QLabel("—")
        self.path_label.setObjectName("faintLabel")
        self.path_label.setFont(theme.mono_font(8))
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # dlouhá cesta nesmí roztahovat panel
        self.path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        # umožni úzké okno – widgety se smí zmenšit
        for _w in (self.status_combo, self.priority_combo, self.category_edit, self.tags_edit):
            _w.setMinimumWidth(46)
        self.status_combo.setMinimumContentsLength(12)
        self.priority_combo.setMinimumContentsLength(4)
        self.category_edit.setMaximumWidth(160)
        self.tags_edit.setMaximumWidth(220)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        chips.addWidget(self.status_combo)
        chips.addWidget(self.priority_combo)
        chips.addWidget(self.flag_btn)
        chips.addWidget(self.category_edit)
        chips.addWidget(self.tags_edit)
        chips.addStretch(1)
        chips.addWidget(self.path_label)

        header = QWidget()
        hv = QVBoxLayout(header)
        hv.setContentsMargins(16, 12, 16, 10)
        hv.setSpacing(6)
        hv.addWidget(self.crumb_label)
        hv.addLayout(title_row)
        hv.addLayout(chips)

        # --- editor ---
        self.editor = MarkdownEditor()
        self.editor.setMinimumWidth(160)

        # --- odkazy na soubory ---
        self.link_list = LinkList()
        self.link_list.setMinimumWidth(80)
        self.link_list.itemDoubleClicked.connect(lambda _: self._open_link())
        self.link_list.filesDropped.connect(self._on_files_dropped)
        open_btn = IconButton("external", "Otevřít soubor")
        open_btn.clicked.connect(self._open_link)
        folder_btn = IconButton("folder", "Otevřít složku")
        folder_btn.clicked.connect(self._open_folder)
        remove_btn = IconButton("close", "Odebrat odkaz")
        remove_btn.clicked.connect(self._remove_link)
        links_box, lb = _section("Soubory", "přetáhni sem soubory", [open_btn, folder_btn, remove_btn])
        links_box.setToolTip("Odkazy na soubory – přetáhni sem soubory")
        lb.addWidget(self.link_list, 1)

        # --- odkazy na jiné úkoly ---
        self.ref_list = QListWidget()
        self.ref_list.setMinimumWidth(80)
        self.ref_list.itemDoubleClicked.connect(lambda _: self._goto_ref())
        add_ref_btn = IconButton("plus", "Přidat odkaz na úkol")
        add_ref_btn.clicked.connect(lambda: self.addRefRequested.emit())
        goto_ref_btn = IconButton("arrow_right", "Přejít na úkol")
        goto_ref_btn.clicked.connect(self._goto_ref)
        rm_ref_btn = IconButton("close", "Odebrat odkaz")
        rm_ref_btn.clicked.connect(self._remove_ref)
        refs_box, rb = _section("Úkoly", "", [add_ref_btn, goto_ref_btn, rm_ref_btn])
        rb.addWidget(self.ref_list, 1)

        # spodní pás: soubory | úkoly vedle sebe
        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.addWidget(links_box)
        bottom_splitter.addWidget(refs_box)
        bottom_splitter.setStretchFactor(0, 1)
        bottom_splitter.setStretchFactor(1, 1)

        # --- rozložení ---
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.editor)
        splitter.addWidget(bottom_splitter)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(HLine())
        layout.addWidget(splitter, 1)

        # --- signály ---
        self.status_combo.currentIndexChanged.connect(self._on_status_combo_changed)
        self.priority_combo.currentIndexChanged.connect(lambda: self._apply_field("_priority", self.priority_combo.currentData()))
        self.category_edit.editingFinished.connect(lambda: self._apply_field("_category", self.category_edit.text().strip()))
        self.tags_edit.editingFinished.connect(self._apply_tags)
        self.flag_btn.toggled.connect(self._on_flag_btn)
        self.done_check.toggled.connect(self._on_done_check)

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
            self.category_edit.clear()
            self.tags_edit.clear()
            self.editor.clear()
            self.link_list.clear()
            self.ref_list.clear()
            self.flag_btn.setChecked(False)
            self.done_check.setChecked(False)
            self.title_label.setText("—")
            self.crumb_label.setText("—")
            self.path_label.setText("—")
            self.setEnabled(False)
            self._loading = False
            return

        self._loading = True
        self.setEnabled(True)
        self._select_data(self.status_combo, node.meta.get("_status"))
        self._select_data(self.priority_combo, node.meta.get("_priority"))
        self.category_edit.setText(node.meta.get("_category", "") or "")
        self.tags_edit.setText(", ".join(node.meta.get("_tags", []) or []))
        self.flag_btn.setChecked(bool(node.meta.get("_flag", False)))
        self.done_check.setChecked(node.meta.get("_status") == "done")
        self.title_label.setText(node.title)
        self.crumb_label.setText(breadcrumb(node.parent) if node.parent is not None else "kořen prostoru")
        self.path_label.setText(node.path.as_posix())
        self.path_label.setToolTip(node.path.as_posix())
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
    def _on_status_combo_changed(self) -> None:
        if self._loading or self.node is None:
            return
        value = self.status_combo.currentData()
        if value == "done":
            n = self.node.incomplete_subtasks()
            if n and not self._confirm_complete(n):
                # zamítnuto – vrať combo na skutečný stav úkolu bez uložení
                self._loading = True
                self._select_data(self.status_combo, self.node.meta.get("_status"))
                self.done_check.setChecked(self.node.meta.get("_status") == "done")
                self._loading = False
                return
        node = self.node
        self._apply_field("_status", value)
        self._loading = True
        self.done_check.setChecked(value == "done")
        self._loading = False
        self.statusChanged.emit(node, value)

    def _on_done_check(self, checked: bool) -> None:
        """Checkbox u názvu = totéž co stav Hotovo / Ke zpracování v comboboxu."""
        if self._loading or self.node is None:
            return
        self._select_data(self.status_combo, "done" if checked else "todo")

    def _confirm_complete(self, count: int) -> bool:
        r = QMessageBox.question(
            self, "Dokončit úkol?",
            f"Úkol „{self.node.title}“ má {count} nedokončených podúkolů.\n"
            "Opravdu ho chceš označit jako hotový?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return r == QMessageBox.StandardButton.Yes

    def _apply_field(self, key: str, value) -> None:
        if self._loading or self.node is None:
            return
        self.node.set_field(key, value)
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
        self.done_check.setChecked(status == "done")
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

    def sync_title(self, title: str) -> None:
        """Po přejmenování zvenčí (F2 ve stromu) obnov název i cestu v hlavičce."""
        if self.node is None:
            return
        self.title_label.setText(title)
        self.path_label.setText(self.node.path.as_posix())

    def _on_flag_btn(self, checked: bool) -> None:
        self._apply_field("_flag", bool(checked))

    # ------------------------------------------------------------------
    # Odkazy
    # ------------------------------------------------------------------
    def _refresh_links(self) -> None:
        self.link_list.clear()
        if self.node is None:
            return
        t = theme.current()
        for link in self.node.links:
            path = link.get("path", "")
            exists = os.path.exists(path)
            item = QListWidgetItem(link.get("name", path))
            item.setIcon(icons.icon("file" if exists else "warning", 14,
                                    t.text2 if exists else t.status_fg["blocked"]))
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
        t = theme.current()
        for rid in self.node.refs:
            target = self.resolver(rid) if self.resolver else None
            title = target.title if target is not None else "(smazaný úkol)"
            item = QListWidgetItem(title)
            item.setIcon(icons.icon("reply", 14, t.text2 if target is not None else t.muted))
            item.setData(REF_ROLE, rid)
            if target is not None:
                item.setToolTip(breadcrumb(target))
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
