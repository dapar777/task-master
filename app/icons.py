"""Kreslené ikony (inline SVG, tahové), obarvené podle tématu.

Místo emoji: škálují se, mají jednotný styl a přebírají barvu textu.
icon("flag") vrací QIcon; pixmap("flag", size, color) hotový obrázek.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from . import theme

# název -> (obsah <svg>, vyplněná?)
_PATHS: dict[str, tuple[str, bool]] = {
    "search": ('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>', False),
    "plus": ('<path d="M12 5v14M5 12h14"/>', False),
    "close": ('<path d="M18 6L6 18M6 6l12 12"/>', False),
    "check": ('<path d="M5 12l5 5L20 7"/>', False),
    "tree": ('<path d="M5 5h6M9 12h10M13 19h6"/><circle cx="5" cy="12" r="1.2" fill="currentColor"/>'
             '<circle cx="9" cy="19" r="1.2" fill="currentColor"/>', False),
    "list": ('<path d="M5 6h14M5 12h14M5 18h14"/>', False),
    "cards": ('<rect x="4" y="4" width="16" height="7" rx="2"/><rect x="4" y="14" width="16" height="6" rx="2"/>', False),
    "flag": ('<path d="M5 4v17M5 4h11l-2 4 2 4H5"/>', True),
    "flag_outline": ('<path d="M5 4v17M5 4h11l-2 4 2 4H5"/>', False),
    "clock": ('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', False),
    "ban": ('<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>', False),
    "rotate": ('<path d="M4 12a8 8 0 0114-5.3L21 9M21 4v5h-5"/>', False),
    "link": ('<path d="M10 13a5 5 0 007 0l3-3a5 5 0 00-7-7l-1 1"/><path d="M14 11a5 5 0 00-7 0l-3 3a5 5 0 007 7l1-1"/>', False),
    "external": ('<path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h7"/><path d="M15 3h6v6M10 14L21 3"/>', False),
    "file": ('<path d="M6 3h8l5 5v13H6z"/><path d="M14 3v5h5"/>', False),
    "folder": ('<path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>', False),
    "arrow_right": ('<path d="M5 12h14M13 6l6 6-6 6"/>', False),
    "reply": ('<path d="M4 6v6a4 4 0 004 4h11M15 12l4 4-4 4"/>', False),
    "chevron_down": ('<path d="M6 9l6 6 6-6"/>', False),
    "chevron_right": ('<path d="M9 6l6 6-6 6"/>', False),
    "command": ('<path d="M4 17l6-5-6-5M12 19h8"/>', False),
    "home": ('<path d="M4 11l8-7 8 7v9a1 1 0 01-1 1h-5v-6h-4v6H5a1 1 0 01-1-1z"/>', False),
    "warning": ('<path d="M12 9v4M12 17h.01M10.3 3.9L2.6 17a2 2 0 001.7 3h15.4a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"/>', False),
    "sun": ('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>', False),
    "moon": ('<path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"/>', False),
    "edit": ('<path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"/>', False),
    "bookmark": ('<path d="M19 21l-7-4-7 4V5a2 2 0 012-2h10a2 2 0 012 2z"/>', False),
    "subtasks": ('<path d="M6 4v8a3 3 0 003 3h9M14 11l4 4-4 4"/>', False),
    "hash": ('<path d="M5 9h14M5 15h14M10 3L8 21M16 3l-2 18"/>', False),
    "doc": ('<path d="M6 3h8l5 5v13H6z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>', False),
    "copy": ('<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 012-2h10"/>', False),
    "scissors": ('<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4L8.5 15.5M8.5 8.5L20 20"/>', False),
    "clipboard": ('<rect x="8" y="3" width="8" height="4" rx="1"/><path d="M16 5h2a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V7a2 2 0 012-2h2"/>', False),
    "text": ('<path d="M4 6h16M4 12h10M4 18h14"/>', False),
    "trash": ('<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>', False),
    "undo": ('<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 010 10h-2"/>', False),
    "dot": ('<circle cx="12" cy="12" r="6"/>', True),
    "chart": ('<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>', False),
    "keyboard": ('<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M8 14h8"/>', False),
    "save": ('<path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/>', False),
    "sliders": ('<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>', False),
}

_cache: dict[tuple, QPixmap] = {}


def svg(name: str, color: str, stroke_width: float = 2.2) -> str:
    body, filled = _PATHS[name]
    fill = color if filled else "none"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{fill}" '
        f'stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" '
        f'stroke-linejoin="round">{body.replace("currentColor", color)}</svg>'
    )


def pixmap(name: str, size: int = 16, color: str | None = None) -> QPixmap:
    color = color or theme.current().text2
    app = QApplication.instance()
    dpr = app.devicePixelRatio() if app else 1.0
    key = (name, size, color, dpr)
    pm = _cache.get(key)
    if pm is not None:
        return pm
    px = int(size * dpr)
    img = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg(name, color).encode("utf-8"))).render(p, QRectF(0, 0, px, px))
    p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    _cache[key] = pm
    return pm


def icon(name: str, size: int = 16, color: str | None = None) -> QIcon:
    return QIcon(pixmap(name, size, color))


_files: dict[tuple, str] = {}


def png_file(name: str, size: int = 12, color: str | None = None) -> str:
    """Cesta k PNG ikony – pro <img> v rich textu (QLabel), kde QIcon nejde."""
    color = color or theme.current().text2
    key = (name, size, color)
    path = _files.get(key)
    if path:
        return path
    d = theme._asset_dir()
    p = d / f"{name}-{size}-{color.lstrip('#')}.png"
    if not p.exists():
        pixmap(name, size, color).save(p.as_posix(), "PNG")
    _files[key] = p.as_posix()
    return _files[key]


def clear_cache() -> None:
    """Po změně tématu – ikony se překreslí v nových barvách."""
    _cache.clear()
