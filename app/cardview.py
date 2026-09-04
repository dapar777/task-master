"""Režim „Bez rušení" – úkoly vyhovující filtru jako karty v jednom sloupci.

Karta: levý pruh v barvě stavu, checkbox, patkový název, cesta, řádek chipů
(stav, kategorie, tagy, počty odkazů, pořadí); vpravo odznak podúkolů,
odpočet odkladu s tlačítkem Obnovit a štítek priority. Úsporná karta má jen
název a cestu. Karty stojí ve skupinách podle stavu s nadpisy.
Po najetí myší se v plovoucím okénku zobrazí text úkolu.
"""

from __future__ import annotations

import html

from PySide6.QtCore import QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import icons, theme
from .constants import STATUSES
from .taskdialog import format_duration
from .tasktree import _chip_text, breadcrumb
from .widgets import Badge, Chip, IconButton, PriorityPill, StatusChip, TitleLabel

CARD_COLUMN_WIDTH = 860


def _incomplete_subtasks(node) -> int:
    """Počet nedokončených podúkolů (rekurzivně přes celý podstrom)."""
    return node.incomplete_subtasks()


def _props_text(node, blocker=None) -> str:
    """Textový souhrn vlastností (stav, priorita, pořadí, kategorie, tagy, odkazy)."""
    if node.snooze_elapsed():
        status = "⏰ Čas vypršel"   # už nečeká – volá po akci
    else:
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
        # šířka se přizpůsobí sloupci; výška roste podle zalomeného obsahu
        sp = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

        t = theme.current()
        status = node.meta.get("_status", "")
        done = status == "done"
        # levý pruh v barvě stavu (kreslí paintEvent); priorita = štítek vpravo
        self._stripe = QColor(theme.status_style(node)[2])
        blocker = resolver(node.blocked_by) if (resolver and node.blocked_by) else None

        # zaškrtávátko stavu (hotovo)
        self.check = QCheckBox()
        self.check.setChecked(done)
        self.check.setToolTip("Hotovo")
        self.check.toggled.connect(self._on_check)

        # název: patkový, vlaječka jako ikona před ním, hotový přeškrtnutý
        self.flagged = bool(node.flag)
        self.title = TitleLabel(node.title, 11.5 if compact else 14.5)
        if done:
            tf = self.title.font()
            tf.setStrikeOut(True)
            self.title.setFont(tf)
            self.title.setStyleSheet(f"color:{t.done_text};")
        self.flag_label = None
        if self.flagged:
            self.flag_label = QLabel()
            self.flag_label.setPixmap(icons.pixmap("flag", 14, t.accent))
            self.flag_label.setToolTip("Vlaječka")

        # pravý shluk: odznak podúkolů, odpočet + Obnovit, popis, priorita
        right = QHBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(6)
        inc = _incomplete_subtasks(node)
        if inc:
            right.addWidget(Badge(f"↳ {inc}", tooltip=f"{inc} nedokončených podúkolů"))
        self.countdown = None
        self.resume_btn = None
        if status == "snoozed":
            self.countdown = StatusChip("snoozed", "", icon="clock", mono=True)
            right.addWidget(self.countdown)
            self.resume_btn = IconButton("rotate", "Odložit znovu o stejný interval",
                                         text="Obnovit", framed=True)
            self.resume_btn.clicked.connect(lambda: self.resumeRequested.emit(self.node))
            right.addWidget(self.resume_btn)
            self.refresh_countdown()
        self.has_body = bool(node.has_body)
        if self.has_body:
            doc = QLabel()
            doc.setPixmap(icons.pixmap("doc", 14, t.muted))
            doc.setToolTip("Úkol má popis")
            right.addWidget(doc)
        right.addWidget(PriorityPill(node.meta.get("_priority", "?")))

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        if self.flag_label is not None:
            title_row.addWidget(self.flag_label, 0, Qt.AlignmentFlag.AlignTop)
            title_row.setSpacing(6)
        title_row.addWidget(self.title, 1)
        title_row.addLayout(right, 0)
        title_row.setAlignment(right, Qt.AlignmentFlag.AlignTop)

        # cesta; úsporná karta si k ní připojí blokující info, ať se neztratí
        path_text = breadcrumb(node)
        if compact and node.blocked_by:
            path_text += "   ·   blokuje: " + (blocker.title if blocker else "(smazaný úkol)")
        elif compact and node.auto_blocked:
            path_text += "   ·   blokováno automaticky"
        self.path = QLabel(path_text)
        self.path.setObjectName("pathLabel")
        self.path.setWordWrap(True)  # ať nediktuje minimální šířku karty

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(2 if compact else 6)
        left.addLayout(title_row)
        left.addWidget(self.path)

        # plná karta: řádek chipů (stav, kategorie, tagy, odkazy, pořadí)
        if not compact:
            props = QHBoxLayout()
            props.setContentsMargins(0, 0, 0, 0)
            props.setSpacing(8)
            icon = "ban" if (node.blocked_by or node.auto_blocked) else None
            chip = StatusChip(status, _chip_text(node), icon=icon)
            if blocker is not None:
                chip.setToolTip(f"Blokuje: {blocker.title}")
            elif node.blocked_by:
                chip.setToolTip("Blokující úkol byl smazán")
            elif node.auto_blocked:
                chip.setToolTip("Blokováno automaticky – podúkoly čekají/blokují")
            props.addWidget(chip)
            cat = node.meta.get("_category", "")
            if cat:
                props.addWidget(Chip(html.escape(cat), t.text2, t.panel))
            for tag in node.meta.get("_tags", []) or []:
                props.addWidget(Chip("#" + html.escape(str(tag)), t.text2, t.panel))
            if node.links:
                c = Chip(str(len(node.links)), t.text2, t.panel, icon="external")
                c.setToolTip(f"{len(node.links)} odkazů na soubory")
                props.addWidget(c)
            if node.refs:
                c = Chip(str(len(node.refs)), t.text2, t.panel, icon="link")
                c.setToolTip(f"{len(node.refs)} odkazů na úkoly")
                props.addWidget(c)
            order = QLabel(f"pořadí {node.order:g}")
            order.setObjectName("faintLabel")
            props.addWidget(order)
            props.addStretch(1)
            left.addLayout(props)

        row = QHBoxLayout(self)
        m = 8 if compact else 12
        row.setContentsMargins(18, m, 14, m)
        row.setSpacing(12)
        row.addWidget(self.check, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(left, 1)

        # náhled textu jako tooltip celé karty (zobrazí se u kurzoru i vpravo)
        self._body_provider = lambda n=node: n.read_body()
        self._tip_loaded = False

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._stripe)
        p.drawRoundedRect(QRectF(1.5, 9, 4, max(4, self.height() - 18)), 2, 2)
        p.end()

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
            self.countdown.setProperty("phase", "none")
            self.countdown.update_status("blocked", "bez termínu", icon="clock")
            self.countdown.setToolTip("Odklad nemá nastavený čas – nastav ho znovu")
            return
        if rem > 0:
            self.countdown.setProperty("phase", "running")
            self.countdown.update_status("snoozed", format_duration(rem), icon="clock")
            self.countdown.setToolTip("Zbývá do konce odkladu")
        else:
            self.countdown.setProperty("phase", "elapsed")
            self.countdown.update_status("blocked", "vypršelo", icon="clock")
            self.countdown.setToolTip("Odklad skončil – úkol čeká na tebe")

    def _on_check(self, checked: bool) -> None:
        self.statusToggled.emit(self.node, "done" if checked else "todo")

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
        self.setObjectName("cardsArea")
        self.setWidgetResizable(True)
        # karty se přizpůsobí šířce sloupce – nikdy vodorovné rolování
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # stránka (nažloutlý podklad) se sloupcem karet uprostřed
        self.container = QWidget()
        self.container.setObjectName("cardsPage")
        outer = QHBoxLayout(self.container)
        outer.setContentsMargins(24, 16, 24, 16)
        # sloupec bere celou šířku až do maxima; rozpěrky (váha 0) vezmou jen
        # to, co zbyde nad maximem, takže sloupec stojí uprostřed
        outer.addStretch(0)
        self.column = QWidget()
        self.column.setMaximumWidth(CARD_COLUMN_WIDTH)
        self.column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.vbox = QVBoxLayout(self.column)
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.setSpacing(10)
        self.vbox.addStretch(1)
        outer.addWidget(self.column, 1)
        outer.addStretch(0)
        self.setWidget(self.container)
        self._cards: dict[str, CardWidget] = {}
        self._stamps: dict[str, tuple] = {}  # otisk obsahu karty (recyklace)
        self._headers: dict[str, QLabel] = {}  # nadpisy skupin (recyklují se)
        self._order: list[str] = []  # cesty v zobrazeném pořadí
        self._selected: set[str] = set()   # všechny označené cesty
        self._focus: str | None = None     # aktuální (fokus) karta
        self._anchor: str | None = None    # kotva pro výběr rozsahu (Shift)
        self.resolver = None               # id -> TaskNode (nastaví hlavní okno)
        self._empty = QLabel("Žádné úkoly nevyhovují filtru.")
        self._empty.setObjectName("faintLabel")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def populate(self, nodes, compact_fn=None, group_fn=None) -> None:
        """Naplní karty.

        compact_fn(node) -> True pro úspornou (nižší) kartu.
        group_fn(node) -> (klíč, nadpis, naléhavé) skupiny; při změně klíče
        se mezi karty vloží nadpis skupiny.
        """
        vpos = self.verticalScrollBar().value()
        # Bez tohoto Qt překresluje po každé přidané kartě a nová karta bez
        # rodiče na okamžik problikne jako samostatné okno mimo aplikaci.
        self.container.setUpdatesEnabled(False)
        try:
            self._rebuild(nodes, compact_fn, group_fn)
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
            node.title, node.flag, node.has_body, compact, theme.current().name,
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
        card = CardWidget(node, parent=self.column,
                          resolver=self.resolver, compact=compact)
        card.selected.connect(self._on_card_clicked)
        card.opened.connect(self.cardOpened)
        card.statusToggled.connect(self.cardStatusToggled)
        card.contextRequested.connect(self._on_card_context)
        card.resumeRequested.connect(self.cardResumeRequested)
        return card

    def _header(self, key: str, label: str, urgent: bool) -> QLabel:
        h = self._headers.get(key)
        if h is None:
            h = QLabel(label.upper(), self.column)
            h.setObjectName("groupHeader")
            self._headers[key] = h
        if h.property("urgent") != ("true" if urgent else "false"):
            h.setProperty("urgent", "true" if urgent else "false")
            h.style().unpolish(h)
            h.style().polish(h)
        return h

    def _rebuild(self, nodes, compact_fn, group_fn) -> None:
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
        used_headers: set[str] = set()

        if not nodes:
            for card in old_cards.values():
                card.setParent(None)
                card.deleteLater()
            for h in self._headers.values():
                h.hide()
            self._empty.setParent(self.column)
            self.vbox.addWidget(self._empty)
            self.vbox.addStretch(1)
            return

        last_group = None
        for node in nodes:
            if group_fn is not None:
                gkey, glabel, gurgent = group_fn(node)
                if gkey != last_group:
                    h = self._header(gkey, glabel, gurgent)
                    h.show()
                    self.vbox.addWidget(h)
                    used_headers.add(gkey)
                    last_group = gkey
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
            self.vbox.addWidget(card)  # roztáhne se na šířku sloupce
            self._cards[key] = card
            self._order.append(key)
            self._stamps[key] = stamp
        self.vbox.addStretch(1)
        for k, h in self._headers.items():
            if k not in used_headers:
                h.hide()

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

    def contextMenuEvent(self, event):
        """Klávesa Menu / Shift+F10: menu pro aktivní kartu (umístí se do jejího středu)."""
        if event.reason() == event.Reason.Keyboard:
            card = self._cards.get(self._focus)
            if card is None:
                event.ignore()
                return
            pos = card.mapToGlobal(card.rect().center())
            path = str(card.node.path)
            if path not in self._selected:
                self._selected = {path}
                self._anchor = path
                self._apply_selection_styles()
                self.cardSelected.emit(card.node)
            self.cardContextMenu.emit(card.node, pos)
            event.accept()
            return
        super().contextMenuEvent(event)

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
