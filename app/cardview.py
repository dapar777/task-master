"""Režim „Bez rušení" – úkoly vyhovující filtru jako velké karty přes celou šířku.

Karta: nahoře velký název, pod ním cesta k úkolu, pak vlastnosti.
Po najetí myší na pravou část karty se v plovoucím okénku zobrazí text úkolu.
"""

from __future__ import annotations

import html

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .constants import PRIORITY_COLORS, STATUS_COLORS, STATUSES
from .taskdialog import format_duration
from .tasktree import breadcrumb


def _incomplete_subtasks(node) -> int:
    """Počet nedokončených podúkolů (rekurzivně přes celý podstrom)."""
    return node.incomplete_subtasks()


def _props_text(node, blocker=None) -> str:
    status = STATUSES.get(node.meta.get("_status", ""), "?")
    if node.blocked_by:
        status += f" ⛔ {blocker.title}" if blocker is not None else " ⛔ (smazaný úkol)"
    elif node.auto_blocked:
        status += " ⛔ auto (podúkoly čekají/blokují)"
    parts = [
        f"Stav: {status}",
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
    selected = Signal(object, object)  # (node, klávesové modifikátory)
    opened = Signal(object)
    statusToggled = Signal(object, str)
    contextRequested = Signal(object, object)  # (node, globální pozice)
    resumeRequested = Signal(object)           # (node) – tlačítko Obnovit

    def __init__(self, node, parent=None, resolver=None, compact=False):
        super().__init__(parent)
        self.node = node
        self.compact = compact
        self.setObjectName("card")
        self.setProperty("selected", "false")  # stejný typ jako v set_selected
        # šířka se přizpůsobí oknu; výška roste podle zalomeného obsahu
        sp = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

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

        # indikace neprázdného popisu přímo v názvu (📝)
        has_body = node.has_body
        title_text = ("🚩 " if node.flag else "") + node.title
        if has_body:
            title_text += "  📝"
        title = QLabel(title_text)
        tcolor = "#888" if done else "#1c1c1c"
        tdec = "text-decoration: line-through;" if done else ""
        tsize = 13 if compact else 16
        title.setStyleSheet(f"font-size:{tsize}px; font-weight:bold; color:{tcolor}; {tdec}")
        title.setWordWrap(True)
        if has_body:
            title.setToolTip("Úkol má popis")

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

        # odpočet odkladu; po doběhnutí místo něj tlačítko Obnovit
        self.countdown = None
        self.resume_btn = None
        if node.meta.get("_status") == "snoozed":
            self.countdown = QLabel()
            self.countdown.setStyleSheet(
                "background:rgba(255,255,255,0.8); color:#8a2a6a;"
                "border:1px solid #d98cc0; border-radius:9px;"
                "padding:0px 7px; font-size:11px; font-weight:bold;"
            )
            title_row.addWidget(self.countdown, 0, Qt.AlignmentFlag.AlignTop)
            self.resume_btn = QToolButton()
            self.resume_btn.setText("↻ Obnovit")
            self.resume_btn.setToolTip("Odložit znovu o stejný interval")
            self.resume_btn.setAutoRaise(True)
            self.resume_btn.setStyleSheet(
                "QToolButton { color:#8a2a6a; font-size:11px; font-weight:bold; }"
            )
            self.resume_btn.clicked.connect(lambda: self.resumeRequested.emit(self.node))
            title_row.addWidget(self.resume_btn, 0, Qt.AlignmentFlag.AlignTop)
            self.refresh_countdown()

        blocker = resolver(node.blocked_by) if (resolver and node.blocked_by) else None

        path_text = breadcrumb(node)
        # úsporná karta si blokující info připojí k cestě, ať se neztratí
        if compact and node.blocked_by:
            path_text += "   ⛔ " + (blocker.title if blocker else "(smazaný úkol)")
        elif compact and node.auto_blocked:
            path_text += "   ⛔ auto"
        path = QLabel(path_text)
        path.setStyleSheet("color:#666; font-size:11px;")
        path.setWordWrap(True)  # ať nediktuje minimální šířku karty

        left = QVBoxLayout()
        left.setSpacing(1 if compact else 3)
        left.addLayout(title_row)
        left.addWidget(path)
        # úsporné zobrazení: bez řádku vlastností (stav/priorita/pořadí)
        if not compact:
            props = QLabel(_props_text(node, blocker))
            props.setStyleSheet("color:#333; font-size:12px;")
            props.setWordWrap(True)
            left.addWidget(props)

        row = QHBoxLayout(self)
        m = 4 if compact else 8
        row.setContentsMargins(10, m, 10, m)
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

    def refresh_countdown(self) -> None:
        """Přepíše zbývající čas; po doběhnutí ukáže výzvu místo odpočtu."""
        if self.countdown is None:
            return
        rem = self.node.snooze_remaining()
        if rem is None:
            # stav bez termínu (vybraný comboboxem) – ať to není prázdný odznak
            self.countdown.setText("⏰ bez termínu")
            self.countdown.setToolTip("Odklad nemá nastavený čas – nastav ho znovu")
            self.countdown.setStyleSheet(
                "background:#ffd9d9; color:#b02020;"
                "border:1px solid #e08080; border-radius:9px;"
                "padding:0px 7px; font-size:11px; font-weight:bold;"
            )
            return
        if rem > 0:
            self.countdown.setText(f"⏳ {format_duration(rem)}")
            self.countdown.setToolTip("Zbývá do konce odkladu")
            self.countdown.setStyleSheet(
                "background:rgba(255,255,255,0.8); color:#8a2a6a;"
                "border:1px solid #d98cc0; border-radius:9px;"
                "padding:0px 7px; font-size:11px; font-weight:bold;"
            )
        else:
            self.countdown.setText("⏰ vypršelo")
            self.countdown.setToolTip("Odklad skončil – úkol čeká na tebe")
            self.countdown.setStyleSheet(
                "background:#ffd9d9; color:#b02020;"
                "border:1px solid #e08080; border-radius:9px;"
                "padding:0px 7px; font-size:11px; font-weight:bold;"
            )

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
        # Přepočet stylu (unpolish/polish) je drahý a volá se pro každou kartu
        # při každém překreslení – u stovek úkolů to je znát. Dělej ho jen
        # tehdy, když se stav výběru opravdu změnil.
        want = "true" if on else "false"
        if self.property("selected") == want:
            return
        self.setProperty("selected", want)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        self.selected.emit(self.node, event.modifiers())
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.opened.emit(self.node)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        # menu operuje na tomto úkolu; když je součástí vícevýběru, ponech ho,
        # jinak kartu vyber jednotlivě (bez modifikátorů) – řeší CardView níž
        self.contextRequested.emit(self.node, event.globalPos())
        event.accept()


class CardView(QScrollArea):
    cardSelected = Signal(object)
    cardOpened = Signal(object)
    cardStatusToggled = Signal(object, str)
    cardContextMenu = Signal(object, object)  # (node, globální pozice)
    cardResumeRequested = Signal(object)      # (node) – tlačítko Obnovit

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        # karty se přizpůsobí šířce okna – nikdy vodorovné rolování
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setContentsMargins(10, 10, 10, 10)
        self.vbox.setSpacing(8)
        self.vbox.addStretch(1)
        self.setWidget(self.container)
        self._cards: dict[str, CardWidget] = {}
        self._stamps: dict[str, tuple] = {}  # otisk obsahu karty (recyklace)
        self._order: list[str] = []  # cesty v zobrazeném pořadí
        self._selected: set[str] = set()   # všechny označené cesty
        self._focus: str | None = None     # aktuální (fokus) karta
        self._anchor: str | None = None    # kotva pro výběr rozsahu (Shift)
        self.resolver = None               # id -> TaskNode (nastaví hlavní okno)
        self._empty = QLabel("Žádné úkoly nevyhovují filtru.")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet("color:#999; font-size:14px;")

    def populate(self, nodes, compact_fn=None) -> None:
        """Naplní karty. compact_fn(node) -> True pro úspornou (nižší) kartu."""
        vpos = self.verticalScrollBar().value()
        # Bez tohoto Qt překresluje po každé přidané kartě a nová karta bez
        # rodiče na okamžik problikne jako samostatné okno mimo aplikaci.
        self.container.setUpdatesEnabled(False)
        try:
            self._rebuild(nodes, compact_fn)
        finally:
            self.container.setUpdatesEnabled(True)

        # znovu použij výběr na nově vytvořené karty (zachovaly se jen existující)
        self._selected = {p for p in self._selected if p in self._cards}
        if self._focus not in self._cards:
            self._focus = None
        self._apply_selection_styles()
        # Pozici rolování obnov až po přepočítání layoutu – karty tu ještě
        # nemají geometrii, takže scrollbar má rozsah 0 a okamžitý zápis
        # (i ensureWidgetVisible) by pohled srazil nahoru.
        QTimer.singleShot(0, lambda v=vpos: self._restore_scroll(v))

    def _card_stamp(self, node, compact: bool):
        """Otisk všeho, co karta vykresluje – shoda = widget lze recyklovat."""
        blocker = None
        if node.blocked_by and self.resolver:
            b = self.resolver(node.blocked_by)
            blocker = b.title if b else ""
        return (
            node.title, node.flag, node.has_body, compact,
            node.meta.get("_status"), node.meta.get("_priority"),
            node.meta.get("_category"), tuple(node.meta.get("_tags") or ()),
            node.blocked_by, node.auto_blocked, blocker,
            node.snooze_elapsed(),  # doběhnutí mění vzhled i zařazení
            len(node.links), len(node.refs), node.order,
            _incomplete_subtasks(node),
        )

    def _new_card(self, node, compact: bool) -> "CardWidget":
        # rodič HNED v konstruktoru – widget bez rodiče je top-level okno,
        # které Qt stihne zobrazit dřív, než ho addWidget vloží do layoutu
        card = CardWidget(node, parent=self.container,
                          resolver=self.resolver, compact=compact)
        card.selected.connect(self._on_card_clicked)
        card.opened.connect(self.cardOpened)
        card.statusToggled.connect(self.cardStatusToggled)
        card.contextRequested.connect(self._on_card_context)
        card.resumeRequested.connect(self.cardResumeRequested)
        return card

    def _rebuild(self, nodes, compact_fn) -> None:
        """Přestaví seznam karet, ale recykluje ty, které se nezměnily.

        Stavba karty i její layout jsou drahé a rostou s celkovým počtem úkolů,
        ne s počtem viditelných. Většina přebudování (změna stavu, editace,
        přidání úkolu) přitom nechá skoro všechny karty beze změny – ty se jen
        znovu zařadí do layoutu místo zahození a nové konstrukce.
        """
        old_cards = self._cards
        old_stamps = getattr(self, "_stamps", {})

        # vyjmi vše z layoutu; widgety si drž (rozhodnutí padne až podle otisku)
        while self.vbox.count():
            item = self.vbox.takeAt(0)
            w = item.widget()
            if w is self._empty:
                w.setParent(None)  # sdílený štítek jen vyjmi, nemaž

        self._cards = {}
        self._order = []
        self._stamps = {}

        if not nodes:
            for card in old_cards.values():
                card.setParent(None)
                card.deleteLater()
            self.vbox.addWidget(self._empty)
            self.vbox.addStretch(1)
            return

        for node in nodes:
            compact = bool(compact_fn(node)) if compact_fn else False
            key = str(node.path)
            stamp = self._card_stamp(node, compact)
            card = old_cards.pop(key, None)
            if card is None or old_stamps.get(key) != stamp:
                if card is not None:
                    card.setParent(None)  # obsah se změnil – postav znovu
                    card.deleteLater()
                card = self._new_card(node, compact)
            else:
                card.node = node  # po load() je uzel nová instance
            self.vbox.addWidget(card)  # roztáhne se na šířku okna
            self._cards[key] = card
            self._order.append(key)
            self._stamps[key] = stamp
        self.vbox.addStretch(1)

        # co zbylo, ve zobrazení už není – okamžité odpojení, aby po zbytek
        # eventloopu neprosvítali „duchové" karet
        for card in old_cards.values():
            card.setParent(None)
            card.deleteLater()

    def _restore_scroll(self, vpos: int) -> None:
        """Vrať pohled tam, kde byl – přebudování samo o sobě nesmí rolovat.

        Nejdřív obnov pozici; teprve když aktivní karta po přeskupení vypadla
        z výřezu, dorovnej na ni (ensureWidgetVisible samotný nestačí – během
        přepočtu layoutu je „vidět" i karta na nulové pozici).
        """
        sb = self.verticalScrollBar()
        sb.setValue(min(vpos, sb.maximum()))
        card = self._cards.get(self._focus)
        if card is None:
            return
        top = card.y()
        bottom = top + card.height()
        view_top = sb.value()
        view_bottom = view_top + self.viewport().height()
        if top < view_top or bottom > view_bottom:
            self.ensureWidgetVisible(card)

    def scroll_to_top(self) -> None:
        self.verticalScrollBar().setValue(0)

    def update_countdowns(self) -> None:
        """Obnoví odpočty na kartách bez přebudování celého seznamu."""
        for card in self._cards.values():
            card.refresh_countdown()

    def _apply_selection_styles(self) -> None:
        for p, card in self._cards.items():
            card.set_selected(p in self._selected)

    def select_path(self, path: str) -> None:
        """Jednotlivý výběr (nahradí případný vícevýběr)."""
        path = str(path)
        self._selected = {path} if path in self._cards else set()
        self._focus = path if path in self._cards else None
        self._anchor = self._focus
        self._apply_selection_styles()
        card = self._cards.get(path)
        if card is not None:
            self.ensureWidgetVisible(card)

    def select_paths(self, paths) -> None:
        """Vícenásobný výběr; fokus = první existující."""
        ps = [str(p) for p in paths if str(p) in self._cards]
        if not ps:
            return
        self._selected = set(ps)
        self._focus = ps[0]
        self._anchor = ps[0]
        self._apply_selection_styles()
        self.ensureWidgetVisible(self._cards[ps[0]])
        self.cardSelected.emit(self._cards[ps[0]].node)

    def selected_nodes(self) -> list:
        """Označené úkoly v zobrazeném pořadí (pro hromadné operace)."""
        return [self._cards[p].node for p in self._order if p in self._selected]

    def current_path(self) -> str | None:
        return self._focus

    def ensure_selection(self) -> None:
        """Pokud nic není vybráno, vyber první kartu (a vyšle signál výběru)."""
        if self._order and self._focus not in self._cards:
            self._move_selection(0)

    # ----- výběr myší -----
    def _on_card_clicked(self, node, mods) -> None:
        path = str(node.path)
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if ctrl:
            if path in self._selected:
                self._selected.discard(path)
            else:
                self._selected.add(path)
            self._focus = path
            self._anchor = path
        elif shift and self._anchor in self._order and path in self._order:
            a, b = self._order.index(self._anchor), self._order.index(path)
            lo, hi = sorted((a, b))
            self._selected = set(self._order[lo:hi + 1])
            self._focus = path
        else:
            self._selected = {path}
            self._focus = path
            self._anchor = path
        self._apply_selection_styles()
        self.cardSelected.emit(node)

    def _on_card_context(self, node, global_pos) -> None:
        # když úkol není součástí vícevýběru, vyber ho jednotlivě, ať menu
        # operuje na tom, na co uživatel klikl pravým tlačítkem
        path = str(node.path)
        if path not in self._selected:
            self._selected = {path}
            self._focus = path
            self._anchor = path
            self._apply_selection_styles()
            self.cardSelected.emit(node)
        self.cardContextMenu.emit(node, global_pos)

    # ----- navigace klávesnicí -----
    def _move_selection(self, delta: int, extend: bool = False) -> None:
        if not self._order:
            return
        if self._focus in self._order:
            idx = self._order.index(self._focus)
            idx = max(0, min(len(self._order) - 1, idx + delta))
        else:
            idx = 0
        path = self._order[idx]
        if extend and self._anchor in self._order:
            a, b = self._order.index(self._anchor), idx
            lo, hi = sorted((a, b))
            self._selected = set(self._order[lo:hi + 1])
            self._focus = path
            self._apply_selection_styles()
            self.ensureWidgetVisible(self._cards[path])
        else:
            self.select_path(path)
        card = self._cards.get(path)
        if card is not None:
            self.cardSelected.emit(card.node)

    def keyPressEvent(self, event):
        key = event.key()
        extend = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Right):
            self._move_selection(+1, extend)
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Left):
            self._move_selection(-1, extend)
        elif key in (Qt.Key.Key_Home,):
            self._move_selection(-len(self._order), extend)
        elif key in (Qt.Key.Key_End,):
            self._move_selection(len(self._order), extend)
        elif key == Qt.Key.Key_A and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._selected = set(self._order)  # vybrat vše
            self._apply_selection_styles()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            card = self._cards.get(self._focus)
            if card is not None:
                self.cardOpened.emit(card.node)
        elif key == Qt.Key.Key_Space:
            card = self._cards.get(self._focus)
            if card is not None:
                card.check.toggle()
        else:
            super().keyPressEvent(event)
