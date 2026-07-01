"""Režim „Bez rušení" – úkoly vyhovující filtru jako velké karty přes celou šířku.

Karta: nahoře velký název, pod ním cesta k úkolu, pak vlastnosti.
Po najetí myší na pravou část karty se v plovoucím okénku zobrazí text úkolu.
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .constants import PRIORITY_COLORS, STATUS_COLORS, STATUSES
from .tasktree import breadcrumb


def _incomplete_subtasks(node) -> int:
    """Počet nedokončených podúkolů (rekurzivně přes celý podstrom)."""
    n = 0
    for child in node.children:
        if child.meta.get("_status") != "done":
            n += 1
        n += _incomplete_subtasks(child)
    return n


def _props_text(node) -> str:
    parts = [
        f"Stav: {STATUSES.get(node.meta.get('_status', ''), '?')}",
        f"Priorita: {node.meta.get('_priority', '?')}",
        f"Pořadí: {node.order}",
    ]
    cat = node.meta.get("_category", "")
    if cat:
        parts.append(f"Kategorie: {cat}")
    tags = node.meta.get("_tags", []) or []
    if tags:
        parts.append("Tagy: " + ", ".join(tags))
    if node.links:
        parts.append(f"📎 {len(node.links)}")
    if node.refs:
        parts.append(f"🔗 {len(node.refs)}")
    return "    ·    ".join(parts)


class CardWidget(QFrame):
    selected = Signal(object)
    opened = Signal(object)
    statusToggled = Signal(object, str)

    def __init__(self, node, parent=None):
        super().__init__(parent)
        self.node = node
        self.setObjectName("card")
        self.setProperty("selected", False)

        status = node.meta.get("_status", "")
        done = status == "done"
        # pozadí: vlevo dle stavu, vpravo dle priority (poměr 3:1), přechod gradientem
        self._status_color = STATUS_COLORS.get(status, "#ffffff")
        p = node.meta.get("_priority")
        self._prio_color = PRIORITY_COLORS.get(p, "#eeeeee")
        self._apply_style()

        # zaškrtávátko stavu (hotovo)
        self.check = QCheckBox()
        self.check.setChecked(done)
        self.check.setToolTip("Hotovo")
        self.check.toggled.connect(self._on_check)

        title = QLabel(("🚩 " if node.flag else "") + node.title)
        tcolor = "#888" if done else "#1c1c1c"
        tdec = "text-decoration: line-through;" if done else ""
        title.setStyleSheet(f"font-size:16px; font-weight:bold; color:{tcolor}; {tdec}")
        title.setWordWrap(True)

        # decentní odznak s počtem nedokončených podúkolů
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        title_row.addWidget(title, 1)
        inc = _incomplete_subtasks(node)
        if inc:
            badge = QLabel(f"↳ {inc}")
            badge.setToolTip(f"{inc} nedokončených podúkolů")
            badge.setStyleSheet(
                "background:rgba(255,255,255,0.75); color:#8a5a00; border:1px solid #e0b060;"
                "border-radius:9px; padding:0px 7px; font-size:11px; font-weight:bold;"
            )
            title_row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        path = QLabel(breadcrumb(node))
        path.setStyleSheet("color:#666; font-size:11px;")

        props = QLabel(_props_text(node))
        props.setStyleSheet("color:#333; font-size:12px;")
        props.setWordWrap(True)

        left = QVBoxLayout()
        left.setSpacing(3)
        left.addLayout(title_row)
        left.addWidget(path)
        left.addWidget(props)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.addWidget(self.check, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(left, 1)

        # náhled textu jako tooltip celé karty (zobrazí se u kurzoru i vpravo)
        self._body_provider = lambda n=node: n.read_body()
        self._tip_loaded = False

    def enterEvent(self, event):
        if not self._tip_loaded:
            text = (self._body_provider() or "(prázdný popis)").strip()[:4000]
            self.setToolTip(
                "<div style='white-space:pre-wrap; max-width:520px'>"
                + html.escape(text)
                + "</div>"
            )
            self._tip_loaded = True
        super().enterEvent(event)

    def _on_check(self, checked: bool) -> None:
        self.statusToggled.emit(self.node, "done" if checked else "todo")

    def _apply_style(self) -> None:
        # vodorovný přechod: stav vlevo (~3/4) -> priorita vpravo (~1/4)
        grad = (
            "qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 {self._status_color}, stop:0.6 {self._status_color}, "
            f"stop:0.9 {self._prio_color}, stop:1 {self._prio_color})"
        )
        self.setStyleSheet(
            f"QFrame#card {{ background:{grad}; border:1px solid #c8c8c8; border-radius:8px; }}"
            f"QFrame#card[selected=\"true\"] {{ background:{grad}; border:2px solid #1a6fd6; }}"
        )

    def set_selected(self, on: bool) -> None:
        self.setProperty("selected", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        self.selected.emit(self.node)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.opened.emit(self.node)
        super().mouseDoubleClickEvent(event)


class CardView(QScrollArea):
    cardSelected = Signal(object)
    cardOpened = Signal(object)
    cardStatusToggled = Signal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setContentsMargins(10, 10, 10, 10)
        self.vbox.setSpacing(8)
        self.vbox.addStretch(1)
        self.setWidget(self.container)
        self._cards: dict[str, CardWidget] = {}
        self._order: list[str] = []  # cesty v zobrazeném pořadí
        self._selected_path: str | None = None
        self._empty = QLabel("Žádné úkoly nevyhovují filtru.")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet("color:#999; font-size:14px;")

    def populate(self, nodes) -> None:
        while self.vbox.count():
            item = self.vbox.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._cards = {}
        self._order = []

        if not nodes:
            self.vbox.addWidget(self._empty)
            self.vbox.addStretch(1)
            return

        for node in nodes:
            card = CardWidget(node)
            card.setFixedWidth(249)  # všechny obdélníky stejně široké, vlevo
            card.selected.connect(self.cardSelected)
            card.opened.connect(self.cardOpened)
            card.statusToggled.connect(self.cardStatusToggled)
            self.vbox.addWidget(card, 0, Qt.AlignmentFlag.AlignLeft)
            key = str(node.path)
            self._cards[key] = card
            self._order.append(key)
        self.vbox.addStretch(1)
        if self._selected_path in self._cards:
            self.select_path(self._selected_path)

    def select_path(self, path: str) -> None:
        self._selected_path = str(path)
        for p, card in self._cards.items():
            card.set_selected(p == self._selected_path)
        card = self._cards.get(self._selected_path)
        if card is not None:
            self.ensureWidgetVisible(card)

    def current_path(self) -> str | None:
        return self._selected_path

    def ensure_selection(self) -> None:
        """Pokud nic není vybráno, vyber první kartu (a vyšle signál výběru)."""
        if self._order and self._selected_path not in self._cards:
            self._move_selection(0)

    # ----- navigace klávesnicí -----
    def _move_selection(self, delta: int) -> None:
        if not self._order:
            return
        if self._selected_path in self._order:
            idx = self._order.index(self._selected_path)
            idx = max(0, min(len(self._order) - 1, idx + delta))
        else:
            idx = 0
        path = self._order[idx]
        self.select_path(path)
        card = self._cards.get(path)
        if card is not None:
            self.cardSelected.emit(card.node)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Right):
            self._move_selection(+1)
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Left):
            self._move_selection(-1)
        elif key in (Qt.Key.Key_Home,):
            self._move_selection(-len(self._order))
        elif key in (Qt.Key.Key_End,):
            self._move_selection(len(self._order))
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            card = self._cards.get(self._selected_path)
            if card is not None:
                self.cardOpened.emit(card.node)
        elif key == Qt.Key.Key_Space:
            card = self._cards.get(self._selected_path)
            if card is not None:
                card.check.toggle()
        else:
            super().keyPressEvent(event)
