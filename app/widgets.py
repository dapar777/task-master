"""Stavební kameny nového vzhledu: chipy, štítky, segmentový přepínač, ikonová tlačítka.

Barvy berou z app/theme.py; po přepnutí tématu nebo zoomu je hlavní okno
zavolá metodou retheme(), pokud si něco (barvu, písmo, rozměr) drží mimo QSS.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
)

from . import icons, theme


class Chip(QLabel):
    """Zaoblený štítek s textem, volitelnou tečkou (barva stavu) a ikonou."""

    def __init__(self, text: str = "", fg: str | None = None, bg: str | None = None,
                 dot: str | None = None, icon: str | None = None, mono: bool = False,
                 parent=None):
        super().__init__(parent)
        self._text = text
        self._dot = dot
        self._icon = icon
        self._mono = mono
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        t = theme.current()
        self.set_colors(fg or t.text2, bg or t.panel)

    def set_colors(self, fg: str, bg: str) -> None:
        self._fg, self._bg = fg, bg
        self.setStyleSheet(theme.chip_qss(fg, bg))
        self._render()

    def plain(self) -> str:
        """Holý text chipu (text() vrací rich text s tečkou/ikonou)."""
        return self._text

    def retheme(self) -> None:
        """Po zoomu: nový stylesheet (odsazení, poloměr) a ikona v nové velikosti."""
        self.set_colors(self._fg, self._bg)

    def set_text(self, text: str, dot: str | None = None, icon: str | None = None) -> None:
        self._text = text
        self._dot = dot
        self._icon = icon
        self._render()

    def _render(self) -> None:
        parts = []
        if self._dot:
            parts.append(f'<span style="color:{self._dot}; font-size:{theme.px(9)}px;">&#9679;</span>')
        if self._icon:
            # ikona jako obrázek uvnitř rich textu – vykreslí se v barvě textu
            sz = theme.px(12)
            path = icons.png_file(self._icon, sz, self._fg)
            parts.append(f'<img src="{path}" width="{sz}" height="{sz}">')
        txt = self._text
        if self._mono:
            fam = ", ".join(f"'{f}'" for f in theme.MONO_FAMILIES)
            txt = f'<span style="font-family:{fam};">{txt}</span>'
        parts.append(txt)
        self.setText("&nbsp;".join(parts))


class StatusChip(Chip):
    """Chip stavu úkolu (barvy z theme.status_style)."""

    def __init__(self, status: str, text: str, parent=None, mono: bool = False,
                 icon: str | None = None):
        fg, bg, dot = theme.status_style(status)
        super().__init__(text, fg, bg, dot=None if icon else dot, icon=icon, mono=mono, parent=parent)

    def update_status(self, status: str, text: str, icon: str | None = None) -> None:
        fg, bg, dot = theme.status_style(status)
        self._text, self._icon, self._dot = text, icon, (None if icon else dot)
        self.set_colors(fg, bg)


class PriorityPill(Chip):
    """Štítek priority „P8“ (barvy z theme.priority_style)."""

    def __init__(self, priority, parent=None, prefix: str = "P"):
        fg, bg, _ = theme.priority_style(priority)
        super().__init__(f"{prefix}{priority}", fg, bg, mono=True, parent=parent)


class Badge(Chip):
    """Decentní odznak (např. „↳ 3“ nedokončených podúkolů)."""

    def __init__(self, text: str, parent=None, tooltip: str = ""):
        t = theme.current()
        super().__init__(text, t.badge_fg, "transparent", parent=parent)
        self._apply_style()
        if tooltip:
            self.setToolTip(tooltip)

    def _apply_style(self) -> None:
        t = theme.current()
        self.setStyleSheet(theme.scaled(
            f"QLabel{{color:{t.badge_fg}; border:1px solid {t.badge_border}; border-radius:9px;"
            f" padding:0 6px; font-size:8pt; font-weight:600; background:transparent;}}"
        ))

    def retheme(self) -> None:
        self._apply_style()
        self._render()


class TitleLabel(QLabel):
    """Zalamovaný název v patkovém písmu.

    Patková písma (Cambria) mají akcenty a dotahy přes hranici řádku, jak ji
    spočítá QLabel – první řádek se pak nahoře ořezával. Přidáváme pár pixelů
    výšky navíc; text je v labelu svisle centrovaný, takže vzniká rezerva
    nahoře i dole.
    """

    PAD = 8  # px bez zoomu

    def __init__(self, text: str = "", pt: float = 14.5, parent=None):
        super().__init__(text, parent)
        self._pt = pt
        self.setFont(theme.title_font(pt))
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def retheme(self) -> None:
        f = theme.title_font(self._pt)
        f.setStrikeOut(self.font().strikeOut())
        self.setFont(f)

    def _pad(self) -> int:
        return theme.px(self.PAD)

    def heightForWidth(self, w: int) -> int:
        h = super().heightForWidth(w)
        return h + self._pad() if h > 0 else h

    def sizeHint(self):
        s = super().sizeHint()
        s.setHeight(s.height() + self._pad())
        return s

    def minimumSizeHint(self):
        s = super().minimumSizeHint()
        s.setHeight(s.height() + self._pad())
        return s


class SectionLabel(QLabel):
    """Malý verzálkový nadpis sekce (FILTRY, SOUBORY…)."""

    def __init__(self, text: str, parent=None):
        super().__init__(text.upper(), parent)
        self.setObjectName("sectionLabel")


class Kbd(QLabel):
    """Zkratka v rámečku (Ctrl+F)."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("kbd")
        self.retheme()

    def retheme(self) -> None:
        self.setFont(theme.mono_font(8))


class HLine(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("hline")
        self.setFrameShape(QFrame.Shape.NoFrame)


class IconButton(QToolButton):
    """Tlačítko jen s kreslenou ikonou (tooltip = popisek)."""

    def __init__(self, icon_name: str, tooltip: str = "", parent=None, size: int = 16,
                 text: str = "", framed: bool = False, color: str | None = None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._size = size
        self._color = color
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)
        if text:
            self.setText(text)
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        if framed:
            self.setProperty("framed", "true")
        self.retheme()

    def set_icon_name(self, name: str) -> None:
        if name != self._icon_name:
            self._icon_name = name
            self.retheme()

    def retheme(self) -> None:
        sz = theme.px(self._size)
        self.setIconSize(QSize(sz, sz))
        self.setIcon(icons.icon(self._icon_name, sz, self._color))


class PrimaryButton(QPushButton):
    def __init__(self, text: str, icon_name: str | None = None, parent=None):
        super().__init__(text, parent)
        self._icon_name = icon_name
        self.setProperty("primary", "true")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retheme()

    def retheme(self) -> None:
        if self._icon_name:
            sz = theme.px(14)
            self.setIconSize(QSize(sz, sz))
            self.setIcon(icons.icon(self._icon_name, sz, theme.current().accent_fg))


class SegmentedControl(QFrame):
    """Přepínač Strom / Seznam / Bez rušení (jeden vybraný segment)."""

    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("segment")
        self._layout = QHBoxLayout(self)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}
        self._icons: dict[str, str] = {}
        self._group.buttonClicked.connect(self._on_clicked)
        self.retheme()

    def add(self, key: str, text: str, icon_name: str | None = None, tooltip: str = "") -> None:
        b = QToolButton(self)
        b.setObjectName("segmentBtn")
        b.setCheckable(True)
        b.setText(text)
        b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            b.setToolTip(tooltip)
        if icon_name:
            self._icons[key] = icon_name
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._buttons[key] = b
        self._group.addButton(b)
        self._layout.addWidget(b)
        self.retheme()

    def set_current(self, key: str) -> None:
        b = self._buttons.get(key)
        if b is not None and not b.isChecked():
            b.setChecked(True)

    def current(self) -> str | None:
        for k, b in self._buttons.items():
            if b.isChecked():
                return k
        return None

    def _on_clicked(self, button) -> None:
        for k, b in self._buttons.items():
            if b is button:
                self.changed.emit(k)
                return

    def set_compact(self, compact: bool) -> None:
        """Úzké okno: jen ikony (popisek zůstává v tooltipu)."""
        style = (Qt.ToolButtonStyle.ToolButtonIconOnly if compact
                 else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for k, b in self._buttons.items():
            if k in self._icons:
                b.setToolButtonStyle(style)
                if compact and not b.toolTip():
                    b.setToolTip(b.text())

    def retheme(self) -> None:
        m = theme.px(2)
        self._layout.setContentsMargins(m, m, m, m)
        self._layout.setSpacing(m)
        sz = theme.px(14)
        for k, name in self._icons.items():
            self._buttons[k].setIconSize(QSize(sz, sz))
            self._buttons[k].setIcon(icons.icon(name, sz))
