"""Stromové / seznamové zobrazení úkolů s podporou drag & drop.

- Přetažení souboru z OS na úkol -> přidá odkaz na soubor (link) do metadat.
- Přetažení úkolu na jiný úkol (jen ve stromovém režimu) -> přesun (reparenting).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from .constants import (
    PRIORITIES,
    PRIORITY_COLORS,
    STATUS_COLORS,
    STATUS_ORDER,
    STATUSES,
)
from .storage import TaskNode

NODE_ROLE = Qt.ItemDataRole.UserRole


def _sort_value(node: TaskNode, key: str):
    if key == "order":
        return (node.order, node.title.lower())
    if key == "priority":
        try:
            return int(node.meta.get("_priority", 0) or 0)
        except (TypeError, ValueError):
            return 0
    if key == "status":
        s = node.meta.get("_status", "")
        return STATUS_ORDER.index(s) if s in STATUS_ORDER else len(STATUS_ORDER)
    if key == "created":
        return node.meta.get("_created", "")
    if key == "modified":
        return node.meta.get("_modified", "")
    return node.title.lower()  # "title" / default


def sort_nodes(nodes, key: str, desc: bool = False):
    return sorted(nodes, key=lambda n: _sort_value(n, key), reverse=desc)


def breadcrumb(node: TaskNode) -> str:
    parts = []
    n = node
    while n is not None:
        parts.append(n.title)
        n = n.parent
    return "  /  ".join(reversed(parts))


class TaskTreeWidget(QTreeWidget):
    taskSelected = Signal(object)        # TaskNode | None
    linkDropped = Signal(object)         # TaskNode (odkaz přidán)
    reparentRequested = Signal(object, object)  # (node, new_parent | None)
    reorderRequested = Signal(object, object, bool)  # (node, ref_node, before) – pořadí
    statusToggled = Signal(object, str)  # (node, new_status) z checkboxu

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tree_mode = True
        self.setColumnCount(3)
        self.setHeaderLabels(["Úkol", "Stav", "Priorita"])
        self.setColumnWidth(0, 280)
        self.setColumnWidth(1, 110)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setUniformRowHeights(True)

        # Drag & drop
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDropIndicatorShown(True)

        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.itemChanged.connect(self._on_item_changed)

    # ------------------------------------------------------------------
    # Naplnění
    # ------------------------------------------------------------------
    def populate(self, roots, tree_mode: bool, match_fn,
                 sort_key: str = "title", sort_desc: bool = False) -> None:
        self._tree_mode = tree_mode
        self._sort_key = sort_key
        self._sort_desc = sort_desc
        selected = self.current_node()
        self.blockSignals(True)
        self.clear()
        if tree_mode:
            for r in self._sorted(roots):
                item = self._build_tree(r, match_fn)
                if item is not None:
                    self.addTopLevelItem(item)
            self.expandAll()
        else:
            nodes = [n for n in self._iter_all(roots) if match_fn(n)]
            for node in self._sorted(nodes):
                self.addTopLevelItem(self._make_item(node, label=breadcrumb(node)))
        self.blockSignals(False)
        if selected is not None:
            self.select_node(selected)

    def _sorted(self, nodes):
        return sort_nodes(
            nodes,
            getattr(self, "_sort_key", "title"),
            getattr(self, "_sort_desc", False),
        )

    def _iter_all(self, roots):
        for r in roots:
            yield r
            yield from r.iter_descendants()

    def _build_tree(self, node: TaskNode, match_fn):
        child_items = []
        for c in self._sorted(node.children):
            ci = self._build_tree(c, match_fn)
            if ci is not None:
                child_items.append(ci)
        if match_fn(node) or child_items:
            item = self._make_item(node)
            for ci in child_items:
                item.addChild(ci)
            return item
        return None

    def _make_item(self, node: TaskNode, label: str | None = None) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        text = label or node.title
        if node.flag:
            text = "🚩 " + text
        status = node.meta.get("_status", "")
        priority = node.meta.get("_priority", "")
        item.setText(1, STATUSES.get(status, str(status)))
        item.setText(2, str(PRIORITIES.get(priority, priority)))
        if status in STATUS_COLORS:
            item.setBackground(1, QBrush(QColor(STATUS_COLORS[status])))
        if priority in PRIORITY_COLORS:
            item.setBackground(2, QBrush(QColor(PRIORITY_COLORS[priority])))

        # zaškrtávací checkbox = hotovo / nehotovo
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(
            0, Qt.CheckState.Checked if status == "done" else Qt.CheckState.Unchecked
        )
        if status == "done":
            f = item.font(0)
            f.setStrikeOut(True)
            item.setFont(0, f)
            item.setForeground(0, QBrush(QColor("#888")))

        n_links = len(node.links)
        n_refs = len(node.refs)
        tip = node.path.as_posix()
        if n_links:
            text += f"  📎{n_links}"
            tip += f"\nsouborů: {n_links}"
        if n_refs:
            text += f"  🔗{n_refs}"
            tip += f"\nodkazů na úkoly: {n_refs}"
        item.setText(0, text)
        item.setToolTip(0, tip)
        item.setData(0, NODE_ROLE, node)
        return item

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        node = item.data(0, NODE_ROLE)
        if node is None:
            return
        checked = item.checkState(0) == Qt.CheckState.Checked
        current = node.meta.get("_status")
        if checked and current != "done":
            self.statusToggled.emit(node, "done")
        elif not checked and current == "done":
            self.statusToggled.emit(node, "todo")

    # ------------------------------------------------------------------
    # Výběr
    # ------------------------------------------------------------------
    def current_node(self) -> TaskNode | None:
        items = self.selectedItems()
        if items:
            return items[0].data(0, NODE_ROLE)
        return None

    def _on_selection_changed(self) -> None:
        self.taskSelected.emit(self.current_node())

    def select_node(self, node: TaskNode) -> bool:
        return self._select(str(node.path), silent=True)

    def select_path(self, path: str) -> bool:
        """Vybere úkol podle cesty a vyvolá signál výběru (načte detail)."""
        return self._select(str(path), silent=False)

    def _select(self, target_path: str, silent: bool) -> bool:
        it = self._find_item_by_path(target_path)
        if it is None:
            return False
        if silent:
            self.blockSignals(True)
        self.setCurrentItem(it)
        if silent:
            self.blockSignals(False)
        return True

    def _find_item_by_path(self, path: str):
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            it = stack.pop()
            if it is None:
                continue
            n = it.data(0, NODE_ROLE)
            if n is not None and str(n.path) == path:
                return it
            for i in range(it.childCount()):
                stack.append(it.child(i))
        return None

    # ------------------------------------------------------------------
    # Drag & drop
    # ------------------------------------------------------------------
    def startDrag(self, supportedActions):
        # zapamatuj si tažený uzel (nezávisle na případné změně výběru během tažení)
        self._drag_node = self.current_node()
        super().startDrag(supportedActions)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        pos = event.position().toPoint()
        target_item = self.itemAt(pos)
        target_node = target_item.data(0, NODE_ROLE) if target_item else None

        # 1) Soubory z OS -> odkazy
        if event.mimeData().hasUrls():
            if target_node is None:
                event.ignore()
                return
            added = False
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    if target_node.add_link(url.toLocalFile()):
                        added = True
            if added:
                self.linkDropped.emit(target_node)
            event.acceptProposedAction()
            return

        # 2) Interní přesun / přeuspořádání (jen ve stromu)
        if not self._tree_mode:
            event.ignore()
            return
        dragged = getattr(self, "_drag_node", None) or self.current_node()
        self._drag_node = None
        if dragged is None:
            event.ignore()
            return
        if target_node is dragged or (target_node and dragged.is_ancestor_of(target_node)):
            event.ignore()
            return

        indicator = self.dropIndicatorPosition()
        Pos = QAbstractItemView.DropIndicatorPosition
        # Drop MEZI položky -> změna vlastního pořadí (případně i přeřazení k rodiči cíle)
        if target_node is not None and indicator in (Pos.AboveItem, Pos.BelowItem):
            before = indicator == Pos.AboveItem
            self.reorderRequested.emit(dragged, target_node, before)
            event.acceptProposedAction()
            return

        # Drop NA položku -> vnoření (reparent); na prázdno -> do kořene
        if target_node is dragged.parent:
            event.ignore()
            return
        self.reparentRequested.emit(dragged, target_node)
        event.acceptProposedAction()
