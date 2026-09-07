"""Stromové / seznamové zobrazení úkolů s podporou drag & drop.

- Přetažení souboru z OS na úkol -> přidá odkaz na soubor (link) do metadat.
- Přetažení úkolu na jiný úkol (jen ve stromovém režimu) -> přesun (reparenting).
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
)

from . import icons, theme
from .constants import PRIORITIES, STATUS_ORDER, STATUSES
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


def sort_flat(nodes, key: str, desc: bool = False):
    """Ploché (seznam/karty) řazení: podúkoly stojí NAD svým nadřazeným úkolem.

    Každý úkol si drží blok se svými podúkoly; hlouběji vnořené jsou výš.
    Uvnitř každé skupiny sourozenců (i mezi kořeny) platí zvolené řazení.
    Rodič, který sám není v `nodes` (odfiltrovaný), blok netvoří – jeho
    viditelné podúkoly se zařadí na úroveň nejbližšího viditelného předka.
    """
    present = set(nodes)

    def visible_parent(n):
        p = n.parent
        while p is not None and p not in present:
            p = p.parent
        return p

    # děti seskupené podle nejbližšího VIDITELNÉHO předka (None = kořenová úroveň)
    groups: dict = {}
    for n in nodes:
        groups.setdefault(visible_parent(n), []).append(n)

    out = []

    def emit(node) -> None:
        for child in sort_nodes(groups.get(node, []), key, desc):
            emit(child)          # podúkoly (a jejich podúkoly) nejdřív
        out.append(node)         # rodič až za nimi

    for root in sort_nodes(groups.get(None, []), key, desc):
        emit(root)
    return out


def _status_text(node) -> str:
    """Text sloupce Stav – u odkladu i zbývající čas / výzva po doběhnutí."""
    status = node.meta.get("_status", "")
    text = STATUSES.get(status, str(status))
    if status == "snoozed":
        # po doběhnutí úkol technicky zůstává „snoozed" (kvůli tlačítku
        # Obnovit), ale uživateli to tak nesmí vypadat – ukaž skutečnost
        rem = node.snooze_remaining()
        if rem is None:
            text = "⏰ Čas vypršel  (bez termínu)"
        elif rem <= 0:
            text = "⏰ Čas vypršel"
        else:
            from .taskdialog import format_duration
            text += f"  ⏳ {format_duration(rem)}"
    if node.blocked_by:
        text += " ⛔"
    elif node.auto_blocked:
        text += " ⛔ auto"
    return text


def breadcrumb(node: TaskNode) -> str:
    parts = []
    n = node
    while n is not None:
        parts.append(n.title)
        n = n.parent
    return "  /  ".join(reversed(parts))


def _chip_text(node) -> str:
    """Text chipu stavu: totéž co _status_text, jen bez piktogramů (ty kreslí chip)."""
    text = _status_text(node)
    for ch in "⏳⏰⛔":
        text = text.replace(ch, " ")
    text = " ".join(text.split())
    if node.auto_blocked:
        text = text.replace(" auto", " · auto")
    return text


class _ChipDelegate(QStyledItemDelegate):
    """Sloupce Stav a Priorita jako chipy místo podbarvených buněk.

    Barvy bere z theme.status_style / priority_style, takže se přepnou
    s tématem. Sloupec 0 (název + checkbox) nechává na výchozím delegátu.
    """

    ROW_H = 30  # px bez zoomu

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width(), max(s.height(), theme.px(self.ROW_H)))

    def paint(self, painter, option, index):
        col = index.column()
        if col == 0:
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
        node = index.siblingAtColumn(0).data(NODE_ROLE)
        if node is None:
            return
        icon_name = None
        dot = None
        if col == 1:
            fg, bg, dot = theme.status_style(node)
            text = _chip_text(node)
            if node.meta.get("_status") == "snoozed":
                icon_name, dot = "clock", None
            elif node.blocked_by or node.auto_blocked:
                icon_name, dot = "ban", None
            font = QFont(opt.font)
            font.setBold(True)
            font.setPointSizeF(max(7.5, opt.font.pointSizeF() - 1))
        else:
            p = node.meta.get("_priority", "")
            if p in ("", None):
                return
            fg, bg, _ramp = theme.priority_style(p)
            text = str(p)
            font = theme.mono_font(8.5)
            font.setBold(True)
        fm = QFontMetrics(font)
        px = theme.px
        pad, h = px(7), px(20)
        w = fm.horizontalAdvance(text) + 2 * pad + (px(14) if (dot or icon_name) else 0)
        r = opt.rect
        w = min(w, r.width() - px(8))
        if w <= 0:
            return
        x, y = r.x() + px(4), r.y() + (r.height() - h) // 2
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(QRect(x, y, w, h), px(6), px(6))
        tx = x + pad
        if dot:
            d = px(6)
            painter.setBrush(QColor(dot))
            painter.drawEllipse(tx, y + h // 2 - d // 2, d, d)
            tx += px(12)
        elif icon_name:
            isz = px(12)
            painter.drawPixmap(tx, y + (h - isz) // 2, icons.pixmap(icon_name, isz, fg))
            tx += px(16)
        painter.setFont(font)
        painter.setPen(QColor(fg))
        avail = x + w - pad - tx
        # v úzkém sloupci nech jen tečku/ikonu – zkrácený text by nic neřekl
        if avail >= px(14):
            painter.drawText(
                QRect(tx, y, avail, h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                fm.elidedText(text, Qt.TextElideMode.ElideRight, avail),
            )
        painter.restore()


class TaskTreeWidget(QTreeWidget):
    taskSelected = Signal(object)        # TaskNode | None
    linkDropped = Signal(object)         # TaskNode (odkaz přidán)
    reparentRequested = Signal(object, object)  # (node, new_parent | None)
    reorderRequested = Signal(object, object, bool)  # (node, ref_node, before) – pořadí
    statusToggled = Signal(object, str)  # (node, new_status) z checkboxu
    renameRequested = Signal(object, str)  # (node, new_title) z inline editace

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tree_mode = True
        self._was_tree_mode = False   # první naplnění: nic sbaleného k zapamatování
        self._collapsed: set[str] = set()  # ručně sbalené úkoly (přežijí přebudování)
        self.resolver = None  # id -> TaskNode (nastaví hlavní okno)
        self.setColumnCount(3)
        self.setHeaderLabels(["Úkol", "Stav", "Priorita"])
        self.setColumnWidth(0, theme.px(300))
        self.setColumnWidth(1, theme.px(150))
        self.setAlternatingRowColors(False)
        self.setIndentation(theme.px(18))
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setUniformRowHeights(True)
        self.setItemDelegate(_ChipDelegate(self))
        hdr = self.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, hdr.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, hdr.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, hdr.ResizeMode.Fixed)
        self.setColumnWidth(2, theme.px(60))

        # Drag & drop
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDropIndicatorShown(True)

        # editace názvu jen programově (F2 / akce), ne dvojklikem
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._editing_item = None
        self._editing_orig = ""

        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.itemChanged.connect(self._on_item_changed)
        self.itemDelegate().closeEditor.connect(self._finish_edit)

    STATUS_COL_W = 150   # plná šířka sloupce Stav (px bez zoomu)
    PRIORITY_COL_W = 60
    MIN_TASK_COL_W = 200  # sloupec Úkol se ošidí až jako poslední

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_columns()

    def retheme(self) -> None:
        """Po zoomu: odsazení, šířky sloupců a výšky řádků (delegát je má od zoomu)."""
        self.setIndentation(theme.px(18))
        self._fit_columns()
        self.doItemsLayout()

    def _fit_columns(self) -> None:
        """Úzký strom: nejdřív se zužuje Stav (chip skončí jen s tečkou), pak Priorita."""
        px = theme.px
        w = self.viewport().width()
        prio = px(self.PRIORITY_COL_W) if w >= px(380) else px(40)
        status = px(self.STATUS_COL_W)
        if w - status - prio < px(self.MIN_TASK_COL_W):
            status = max(px(34), w - prio - px(self.MIN_TASK_COL_W))
        if self.columnWidth(1) != status:
            self.setColumnWidth(1, status)
        if self.columnWidth(2) != prio:
            self.setColumnWidth(2, prio)

    # ------------------------------------------------------------------
    # Inline přejmenování
    # ------------------------------------------------------------------
    def edit_title(self, node: TaskNode) -> bool:
        it = self._find_item_by_path(str(node.path))
        if it is None:
            return False
        self.blockSignals(True)
        it.setText(0, node.title)  # bez odznaků
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
        self.blockSignals(False)
        self._editing_item = it
        self._editing_orig = node.title
        self.setCurrentItem(it)
        self.editItem(it, 0)
        return True

    def _finish_edit(self, editor, hint) -> None:
        it = self._editing_item
        if it is None:
            return
        self._editing_item = None
        node = it.data(0, NODE_ROLE)
        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
        new_title = it.text(0).strip()
        if node is not None and new_title and new_title != self._editing_orig:
            self.renameRequested.emit(node, new_title)

    # ------------------------------------------------------------------
    # Naplnění
    # ------------------------------------------------------------------
    def populate(self, roots, tree_mode: bool, match_fn,
                 sort_key: str = "title", sort_desc: bool = False) -> None:
        self._tree_mode = tree_mode
        self._sort_key = sort_key
        self._sort_desc = sort_desc
        selected = self.current_node()
        # sbalený stav si pamatuj i přes přepnutí do plochého režimu (kde žádný
        # není) – po návratu do stromu tak zůstane, jak si ho uživatel nastavil
        if self._was_tree_mode:
            self._collapsed = self._collapsed_paths()
        self._was_tree_mode = tree_mode
        vpos = self.verticalScrollBar().value()
        self.blockSignals(True)
        self.clear()
        if tree_mode:
            for r in self._sorted(roots):
                item = self._build_tree(r, match_fn)
                if item is not None:
                    self.addTopLevelItem(item)
            # nové položky výchozí rozbalené, ručně sbalené zůstanou sbalené
            self.expandAll()
            self._restore_collapsed(self._collapsed)
        else:
            nodes = [n for n in self._iter_all(roots) if match_fn(n)]
            for node in sort_flat(nodes, sort_key, sort_desc):
                self.addTopLevelItem(self._make_item(node, label=breadcrumb(node)))
        self.blockSignals(False)
        if selected is not None:
            self.select_node(selected)
        # obnov pozici rolování (select_node sám o sobě neroluje)
        self.verticalScrollBar().setValue(vpos)

    @staticmethod
    def _collapse_key(node: TaskNode) -> str:
        """Klíč sbaleného stavu: stabilní _id (přežije přejmenování i přesun),
        cesta jen jako záloha pro úkoly bez _id."""
        return node.task_id or str(node.path)

    def _collapsed_paths(self) -> set[str]:
        """Úkoly, které má uživatel ručně sbalené (přežijí přebudování)."""
        out = set()
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            it = stack.pop()
            if it is None:
                continue
            n = it.data(0, NODE_ROLE)
            if n is not None and it.childCount() and not it.isExpanded():
                out.add(self._collapse_key(n))
            for i in range(it.childCount()):
                stack.append(it.child(i))
        return out

    def _restore_collapsed(self, collapsed: set[str]) -> None:
        if not collapsed:
            return
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            it = stack.pop()
            if it is None:
                continue
            n = it.data(0, NODE_ROLE)
            if n is not None and self._collapse_key(n) in collapsed:
                it.setExpanded(False)
            for i in range(it.childCount()):
                stack.append(it.child(i))

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
            item.setIcon(0, icons.icon("flag", 14, theme.current().accent))
        status = node.meta.get("_status", "")
        priority = node.meta.get("_priority", "")
        # texty sloupců zůstávají (řazení, přístupnost); kreslí je chipový delegát
        item.setText(1, _status_text(node))
        item.setText(2, str(PRIORITIES.get(priority, priority)))

        # zaškrtávací checkbox = hotovo / nehotovo
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(
            0, Qt.CheckState.Checked if status == "done" else Qt.CheckState.Unchecked
        )
        if status == "done":
            f = item.font(0)
            f.setStrikeOut(True)
            item.setFont(0, f)
            item.setForeground(0, QBrush(QColor(theme.current().done_text)))

        n_links = len(node.links)
        n_refs = len(node.refs)
        tip = node.path.as_posix()
        if node.blocked_by:
            blocker = self.resolver(node.blocked_by) if self.resolver else None
            tip += "\nblokuje: " + (blocker.title if blocker else "(smazaný úkol)")
        elif node.auto_blocked:
            tip += "\nautomaticky blokováno (všechny podúkoly čekají/blokují)"
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

    def selected_nodes(self) -> list[TaskNode]:
        """Všechny označené úkoly (pro hromadné operace)."""
        out = []
        for it in self.selectedItems():
            n = it.data(0, NODE_ROLE)
            if n is not None:
                out.append(n)
        return out

    def select_paths(self, paths, emit: bool = True) -> bool:
        """Označí více úkolů podle cest; aktuální = první nalezený."""
        items = [self._find_item_by_path(str(p)) for p in paths]
        items = [it for it in items if it is not None]
        if not items:
            return False
        self.blockSignals(True)
        self.clearSelection()
        for it in items:
            self._expand_ancestors(it)  # skrytá pod sbaleným rodičem by nebyla vidět
        # nejdřív aktuální (setCurrentItem výběr přenastaví), pak doplň ostatní
        self.setCurrentItem(items[0])
        for it in items:
            it.setSelected(True)
        self.blockSignals(False)
        if emit:
            self.taskSelected.emit(self.current_node())
        return True

    def _on_selection_changed(self) -> None:
        self.taskSelected.emit(self.current_node())

    def select_node(self, node: TaskNode) -> bool:
        # obnova výběru při přebudování: předky NErozbaluj – uživatel mohl větev
        # s vybraným úkolem právě sbalit a to je novější záměr než starý výběr
        return self._select(str(node.path), silent=True, expand=False)

    def select_path(self, path: str) -> bool:
        """Vybere úkol podle cesty a vyvolá signál výběru (načte detail)."""
        return self._select(str(path), silent=False)

    def _select(self, target_path: str, silent: bool, expand: bool = True) -> bool:
        it = self._find_item_by_path(target_path)
        if it is None:
            return False
        # při ExtendedSelection setCurrentItem položku NEoznačí – musíme sami;
        # signály blokuj a vyšli jen jednou s finálním stavem (jinak přechodné None)
        self.blockSignals(True)
        self.clearSelection()
        if expand:
            self._expand_ancestors(it)  # skrytá pod sbaleným rodičem by nebyla vidět
        self.setCurrentItem(it)
        it.setSelected(True)
        self.blockSignals(False)
        if not silent:
            self.taskSelected.emit(self.current_node())
        return True

    def update_countdowns(self, nodes) -> None:
        """Přepíše sloupec Stav u odložených úkolů (bez přebudování stromu)."""
        want = {str(n.path) for n in nodes}
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            it = stack.pop()
            if it is None:
                continue
            n = it.data(0, NODE_ROLE)
            if n is not None and str(n.path) in want:
                self.blockSignals(True)
                it.setText(1, _status_text(n))
                self.blockSignals(False)
            for i in range(it.childCount()):
                stack.append(it.child(i))

    def visible_paths(self) -> list[str]:
        """Cesty úkolů shora dolů tak, jak jsou právě vykreslené.

        Pořadí bere z widgetu (respektuje řazení i filtr), ne z modelu.
        Položky pod sbalenou větví se počítají taky – ve stromu pořád patří
        na svoje místo, jen nejsou vidět.
        """
        out = []

        def walk(item):
            n = item.data(0, NODE_ROLE)
            if n is not None:
                out.append(str(n.path))
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.topLevelItemCount()):
            walk(self.topLevelItem(i))
        return out

    def _expand_ancestors(self, item) -> None:
        p = item.parent()
        while p is not None:
            p.setExpanded(True)
            p = p.parent()

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
