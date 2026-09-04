"""Vizuální tokeny a téma aplikace (Solarized, světlé / tmavé).

Jediné místo, kde se definují barvy, písma a QSS. Ostatní moduly se ptají
funkcemi (status_style, priority_style, title_font…) a nikde nemají hex
natvrdo. Přepnutí tématu = apply(app, "dark") a překreslení.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QColor, QFont, QPalette

# ----------------------------------------------------------------------------
# Solarized základ
# ----------------------------------------------------------------------------
BASE03, BASE02, BASE01, BASE00 = "#002b36", "#073642", "#586e75", "#657b83"
BASE0, BASE1, BASE2, BASE3 = "#839496", "#93a1a1", "#eee8d5", "#fdf6e3"
YELLOW, ORANGE, RED, MAGENTA = "#b58900", "#cb4b16", "#dc322f", "#d33682"
VIOLET, BLUE, CYAN, GREEN = "#6c71c4", "#268bd2", "#2aa198", "#859900"

# rampa priority 1 (zelená) … 10 (červená) na Solarized odstínech
PRIORITY_RAMP = [
    "#859900", "#8f9700", "#9a9400", "#a89000", "#b58900",
    "#bd7a05", "#c5680c", "#cb4b16", "#d43f22", "#dc322f",
]


def mix(a: str, b: str, t: float) -> str:
    """Smíchá barvu a (podíl t) s barvou b (1 - t); vrací hex."""
    ca, cb = QColor(a), QColor(b)
    r = ca.red() * t + cb.red() * (1 - t)
    g = ca.green() * t + cb.green() * (1 - t)
    bl = ca.blue() * t + cb.blue() * (1 - t)
    return "#%02x%02x%02x" % (round(r), round(g), round(bl))


@dataclass(frozen=True)
class Tokens:
    name: str
    canvas: str      # plátno (pozadí obsahu)
    panel: str       # postranní panel, lišty
    paper: str       # pole, seznam, karta ve stromu
    card: str        # karta v Bez rušení (nažloutlá, ne bílá)
    cards_bg: str    # podklad pod kartami (o stupeň tmavší než karta)
    line: str        # jemná linka
    border: str      # okraj pole / tlačítka
    dashed: str      # čárkovaný okraj („přidat“)
    text: str
    text2: str       # vedlejší text
    muted: str       # popisky, placeholder
    faint: str       # nejslabší text (hex v monospace apod.)
    accent: str
    accent_fg: str
    accent_hover: str
    hover: str       # pozadí při najetí
    selection: str   # pozadí výběru v seznamech
    tint: float      # síla podbarvení chipů
    status_dot: dict  # stav -> barva tečky/pruhu
    status_fg: dict   # stav -> barva textu chipu
    priority_fg: tuple  # 4 skupiny: 1–3, 4–6, 7–8, 9–10
    badge_fg: str
    badge_border: str
    done_text: str   # přeškrtnutý hotový úkol


LIGHT = Tokens(
    name="light",
    canvas=BASE3, panel=BASE2, paper="#fffdf6", card=BASE3, cards_bg="#f3ecd6", line="#e6dfc8",
    border="#d9d2bb", dashed="#c9c1a6",
    text=BASE02, text2=BASE01, muted=BASE1, faint=BASE0,
    accent=ORANGE, accent_fg=BASE3, accent_hover="#b3410f",
    hover="#f5eedb", selection="#f6e3d6", tint=0.14,
    status_dot={
        "todo": BASE01, "in_progress": BLUE, "waiting": YELLOW,
        "snoozed": YELLOW, "blocked": RED, "done": GREEN,
    },
    status_fg={
        "todo": BASE01, "in_progress": "#1c6fa8", "waiting": "#8a6800",
        "snoozed": "#8a6800", "blocked": "#b8221f", "done": "#667500",
    },
    priority_fg=("#667500", "#8a6800", "#a63c10", "#b8221f"),
    badge_fg="#8a5a00", badge_border="#e0b060",
    done_text=BASE1,
)

DARK = Tokens(
    name="dark",
    canvas=BASE03, panel=BASE02, paper="#0b3a47", card="#0b3a47", cards_bg=BASE03, line="#12505f",
    border="#12505f", dashed="#1f5f6e",
    text=BASE2, text2=BASE1, muted=BASE00, faint=BASE01,
    accent=ORANGE, accent_fg=BASE3, accent_hover="#e0602a",
    hover="#0d4352", selection="#1b4a58", tint=0.25,
    status_dot={
        "todo": BASE1, "in_progress": BLUE, "waiting": YELLOW,
        "snoozed": YELLOW, "blocked": RED, "done": GREEN,
    },
    status_fg={
        "todo": BASE1, "in_progress": "#6cb6ea", "waiting": "#e0b23a",
        "snoozed": "#e0b23a", "blocked": "#f0645f", "done": "#b5c94a",
    },
    priority_fg=("#b5c94a", "#e0b23a", "#f0a07a", "#f0645f"),
    badge_fg="#e0b23a", badge_border="#8a6800",
    done_text=BASE00,
)

THEMES = {"light": LIGHT, "dark": DARK}
_current = LIGHT


def current() -> Tokens:
    return _current


def is_dark() -> bool:
    return _current.name == "dark"


# ----------------------------------------------------------------------------
# Sémantické styly
# ----------------------------------------------------------------------------
def status_style(node_or_status) -> tuple[str, str, str]:
    """(text, pozadí, tečka) chipu stavu pro úkol nebo klíč stavu."""
    st = node_or_status if isinstance(node_or_status, str) else node_or_status.meta.get("_status", "")
    t = _current
    dot = t.status_dot.get(st, t.status_dot["todo"])
    fg = t.status_fg.get(st, t.status_fg["todo"])
    return fg, mix(dot, t.paper, t.tint), dot


def priority_hex(p) -> str:
    """Odstín rampy pro prioritu 1–10 (mimo rozsah -> střed)."""
    try:
        i = max(1, min(10, int(p)))
    except (TypeError, ValueError):
        i = 5
    return PRIORITY_RAMP[i - 1]


def priority_style(p) -> tuple[str, str, str]:
    """(text, pozadí, odstín rampy) štítku priority."""
    try:
        i = max(1, min(10, int(p)))
    except (TypeError, ValueError):
        i = 5
    t = _current
    group = 0 if i <= 3 else 1 if i <= 6 else 2 if i <= 8 else 3
    ramp = PRIORITY_RAMP[i - 1]
    return t.priority_fg[group], mix(ramp, t.paper, t.tint + 0.02), ramp


def chip_qss(fg: str, bg: str, radius: int = 6, padding: str = "1px 7px") -> str:
    return (
        f"QLabel{{background:{bg}; color:{fg}; border-radius:{radius}px;"
        f" padding:{padding}; font-weight:600;}}"
    )


# ----------------------------------------------------------------------------
# Písma
# ----------------------------------------------------------------------------
UI_FAMILIES = ["Segoe UI", "Noto Sans", "DejaVu Sans", "sans-serif"]
TITLE_FAMILIES = ["Cambria", "Georgia", "Noto Serif", "DejaVu Serif", "serif"]
MONO_FAMILIES = ["Cascadia Mono", "Consolas", "DejaVu Sans Mono", "monospace"]


def _font(families, pt: float, weight=QFont.Weight.Normal) -> QFont:
    f = QFont()
    f.setFamilies(families)
    f.setPointSizeF(pt)
    f.setWeight(weight)
    return f


def ui_font(pt: float = 10, weight=QFont.Weight.Normal) -> QFont:
    return _font(UI_FAMILIES, pt, weight)


def title_font(pt: float = 14, weight=QFont.Weight.DemiBold) -> QFont:
    return _font(TITLE_FAMILIES, pt, weight)


def mono_font(pt: float = 9) -> QFont:
    return _font(MONO_FAMILIES, pt)


# ----------------------------------------------------------------------------
# QSS
# ----------------------------------------------------------------------------
_CHECK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{c}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M5 12l5 5L20 7"/></svg>'
)
_CHEVRON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{c}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M6 9l6 6 6-6"/></svg>'
)


_CHEVRON_RIGHT_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{c}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M9 6l6 6-6 6"/></svg>'
)


def _asset_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation) or tempfile.gettempdir()
    d = Path(base) / "taskmaster-theme"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_asset(name: str, content: str) -> str:
    p = _asset_dir() / name
    try:
        if not p.exists() or p.read_text(encoding="utf-8") != content:
            p.write_text(content, encoding="utf-8")
    except OSError:
        pass
    return p.as_posix()


def build_qss(t: Tokens) -> str:
    check = _write_asset(f"check-{t.name}.svg", _CHECK_SVG.format(c=t.accent_fg))
    chevron = _write_asset(f"chevron-{t.name}.svg", _CHEVRON_SVG.format(c=t.text2))
    chevron_right = _write_asset(f"chevron-right-{t.name}.svg", _CHEVRON_RIGHT_SVG.format(c=t.text2))
    sel_tint = mix(t.accent, t.paper, 0.10)
    green = t.status_dot["done"]
    return f"""
QMainWindow, QDialog, QMessageBox, QInputDialog, QFileDialog {{ background: {t.canvas}; }}
QWidget {{ color: {t.text}; }}
QLabel {{ background: transparent; }}
QToolTip {{ background: {t.text}; color: {t.canvas}; border: 0; border-radius: 6px; padding: 6px 8px; }}

QMenuBar {{ background: {t.panel}; border-bottom: 1px solid {t.line}; padding: 1px 6px; }}
QMenuBar::item {{ padding: 4px 8px; border-radius: 6px; background: transparent; }}
QMenuBar::item:selected {{ background: {t.hover}; }}
QMenu {{ background: {t.paper}; border: 1px solid {t.border}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 6px 28px 6px 10px; border-radius: 6px; }}
QMenu::item:selected {{ background: {sel_tint}; color: {t.text}; }}
QMenu::item:disabled {{ color: {t.muted}; }}
QMenu::separator {{ height: 1px; background: {t.line}; margin: 6px 8px; }}
QMenu::icon {{ padding-left: 6px; }}
QMenu::icon:checked {{ background: {sel_tint}; border: 1px solid {t.accent}; border-radius: 5px; }}
QMenu::indicator {{ width: 14px; height: 14px; left: 8px; }}
QMenu::indicator:non-exclusive:checked, QMenu::indicator:exclusive:checked {{ image: url("{check}"); background: {green}; border-radius: 4px; }}
QMenu::right-arrow {{ image: url("{chevron_right}"); width: 12px; height: 12px; right: 8px; }}

QStatusBar {{ background: {t.panel}; border-top: 1px solid {t.line}; color: {t.text2}; }}
QStatusBar::item {{ border: 0; }}
QStatusBar QLabel {{ color: {t.text2}; padding: 0 6px; }}

QSplitter::handle {{ background: {t.line}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

QFrame#headerBar {{ background: {t.canvas}; border-bottom: 1px solid {t.line}; }}
QFrame#sidePanel {{ background: {t.panel}; }}
QFrame#chipBar {{ background: {t.canvas}; border-bottom: 1px solid {t.line}; }}
QFrame#segment {{ background: {t.panel}; border: 1px solid {t.border}; border-radius: 8px; }}
QToolButton#segmentBtn {{ border: 0; border-radius: 6px; padding: 3px 10px; font-weight: 600; color: {t.text2}; background: transparent; }}
QToolButton#segmentBtn:hover {{ color: {t.text}; }}
QToolButton#segmentBtn:checked {{ background: {t.paper}; color: {t.text}; }}
QLabel#sectionLabel {{ color: {t.muted}; font-size: 8pt; font-weight: 700; }}
QLabel#groupHeader {{ color: {t.muted}; font-size: 8pt; font-weight: 700; padding: 6px 4px 0 4px; }}
QScrollArea#cardsArea, QWidget#cardsPage {{ background: {t.cards_bg}; }}
QFrame#card {{ background: {t.card}; border: 1px solid {t.line}; border-radius: 10px; }}
QFrame#card:hover {{ border-color: {t.border}; }}
QFrame#card[selected="true"] {{ border: 2px solid {t.accent}; }}
QFrame#card QCheckBox::indicator {{ width: 17px; height: 17px; }}
QFrame#filterHost {{ background: {t.panel}; border-bottom: 1px solid {t.line}; }}
QLabel#groupHeader[urgent="true"] {{ color: {t.status_fg["blocked"]}; }}
QLabel#pathLabel {{ color: {t.text2}; }}
QLabel#faintLabel {{ color: {t.muted}; }}
QLabel#kbd {{ color: {t.muted}; border: 1px solid {t.line}; border-radius: 4px; padding: 0 4px; font-size: 8pt; }}
QLabel#hint {{ color: {t.text2}; }}
QFrame#hline {{ background: {t.line}; max-height: 1px; min-height: 1px; border: 0; }}

QTreeWidget, QTreeView, QListWidget, QListView {{
  background: {t.card}; border: 1px solid {t.line}; border-radius: 8px; outline: 0;
  alternate-background-color: {t.card}; show-decoration-selected: 1; padding: 2px;
}}
QTextEdit, QPlainTextEdit {{ background: {t.paper}; }}
QTreeWidget::item, QListWidget::item {{ padding: 3px 4px; border-radius: 6px; }}
QTreeWidget::item:hover, QListWidget::item:hover {{ background: {t.hover}; }}
QTreeWidget::item:selected, QListWidget::item:selected {{ background: {t.selection}; color: {t.text}; }}
QTreeWidget::branch {{ background: transparent; }}
QTreeWidget::branch:selected {{ background: {t.selection}; }}
QTreeWidget::branch:hover {{ background: {t.hover}; }}
QHeaderView::section {{
  background: transparent; color: {t.muted}; font-size: 8pt; font-weight: 700;
  border: 0; border-bottom: 1px solid {t.line}; padding: 5px 6px;
}}
QTreeWidget::indicator, QCheckBox::indicator {{
  width: 16px; height: 16px; border: 1.5px solid {t.muted}; border-radius: 5px; background: {t.paper};
}}
QTreeWidget::indicator:hover, QCheckBox::indicator:hover {{ border-color: {t.text2}; }}
QTreeWidget::indicator:checked, QCheckBox::indicator:checked {{
  background: {green}; border-color: {green}; image: url("{check}");
}}
QCheckBox {{ spacing: 8px; background: transparent; }}

QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit, QKeySequenceEdit {{
  background: {t.paper}; border: 1px solid {t.border}; border-radius: 8px; padding: 4px 8px;
  selection-background-color: {t.accent}; selection-color: {t.accent_fg};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus, QKeySequenceEdit:focus {{
  border: 1.5px solid {t.accent};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {t.muted}; background: {t.panel}; }}
QComboBox::drop-down {{ border: 0; width: 22px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url("{chevron}"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
  background: {t.paper}; color: {t.text}; border: 1px solid {t.border}; border-radius: 8px; padding: 4px; outline: 0;
  selection-background-color: {t.hover}; selection-color: {t.text};
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; border: 0; background: transparent; }}
QSpinBox::up-arrow {{ image: url("{chevron}"); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url("{chevron}"); width: 10px; height: 10px; }}

QPushButton {{
  background: {t.paper}; color: {t.text}; border: 1px solid {t.border}; border-radius: 8px;
  padding: 5px 12px; font-weight: 500; min-height: 20px;
}}
QPushButton:hover {{ background: {t.hover}; border-color: {t.muted}; }}
QPushButton:pressed {{ background: {t.panel}; }}
QPushButton:disabled {{ color: {t.muted}; }}
QPushButton:default {{ border-color: {t.accent}; }}
QPushButton[primary="true"] {{ background: {t.accent}; color: {t.accent_fg}; border-color: {t.accent}; font-weight: 600; }}
QPushButton[primary="true"]:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
QPushButton[quiet="true"] {{ background: transparent; border-color: transparent; color: {t.text2}; }}
QPushButton[quiet="true"]:hover {{ background: {t.hover}; color: {t.text}; }}

QToolButton {{ border: 1px solid transparent; border-radius: 6px; padding: 3px 6px; background: transparent; color: {t.text2}; }}
QToolButton:hover {{ background: {t.hover}; color: {t.text}; }}
QToolButton:pressed {{ background: {t.panel}; }}
QToolButton:checked {{ background: {t.panel}; color: {t.text}; border-color: {t.border}; }}
QToolButton[framed="true"] {{ border-color: {t.border}; background: {t.paper}; color: {t.text}; padding: 4px 10px; }}
QToolButton[framed="true"]:hover {{ background: {t.hover}; }}
QToolButton::menu-indicator {{ image: none; }}
QToolBar {{ background: transparent; border: 0; border-bottom: 1px solid {t.line}; spacing: 2px; padding: 3px 4px; }}
QToolBar QToolButton {{ font-weight: 600; min-width: 20px; }}
QToolBar::separator {{ width: 1px; background: {t.line}; margin: 6px 5px; }}

QGroupBox {{
  border: 1px solid {t.line}; border-radius: 10px; margin-top: 10px; padding-top: 8px;
  font-weight: 600; color: {t.text2}; background: transparent;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {t.muted}; font-size: 8pt; font-weight: 700; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t.muted}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.border}; border-radius: 4px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {t.muted}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
QScrollArea {{ border: 0; background: transparent; }}

QSlider {{ min-height: 22px; }}
QSlider::groove:horizontal {{ height: 4px; background: {t.line}; border-radius: 2px; margin: 0 9px; }}
QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {t.paper}; border: 2px solid {t.accent}; width: 14px; height: 14px; margin: -7px -9px; border-radius: 9px; }}
QSlider::handle:horizontal:hover {{ background: {t.hover}; }}

QDialogButtonBox QPushButton {{ min-width: 84px; }}
QTabBar::tab {{ padding: 6px 12px; }}
"""


def palette(t: Tokens) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: t.canvas,
        QPalette.ColorRole.WindowText: t.text,
        QPalette.ColorRole.Base: t.paper,
        QPalette.ColorRole.AlternateBase: t.canvas,
        QPalette.ColorRole.Text: t.text,
        QPalette.ColorRole.Button: t.paper,
        QPalette.ColorRole.ButtonText: t.text,
        QPalette.ColorRole.Highlight: t.accent,
        QPalette.ColorRole.HighlightedText: t.accent_fg,
        QPalette.ColorRole.ToolTipBase: t.text,
        QPalette.ColorRole.ToolTipText: t.canvas,
        QPalette.ColorRole.PlaceholderText: t.muted,
        QPalette.ColorRole.Mid: t.border,
        QPalette.ColorRole.Dark: t.muted,
        QPalette.ColorRole.Light: t.paper,
        QPalette.ColorRole.Link: t.accent,
        QPalette.ColorRole.BrightText: t.accent_fg,
    }
    for role, hexv in roles.items():
        p.setColor(role, QColor(hexv))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(t.muted))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(t.muted))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(t.muted))
    return p


def apply(app, name: str = "light") -> Tokens:
    """Nastaví téma pro celou aplikaci (styl Fusion + paleta + QSS + písmo)."""
    global _current
    _current = THEMES.get(name, LIGHT)
    app.setStyle("Fusion")
    app.setPalette(palette(_current))
    app.setFont(ui_font(10))
    app.setStyleSheet(build_qss(_current))
    return _current
