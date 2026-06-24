"""Moderní ikona aplikace – zaškrtnutý checkbox, kreslená v kódu (bez bitmap souborů)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _draw(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    m = size * 0.09
    rect = QRectF(m, m, size - 2 * m, size - 2 * m)
    radius = size * 0.24

    # zaoblený dlaždicový podklad s moderním přechodem (modrá -> zelená)
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0.0, QColor("#4f7cff"))
    grad.setColorAt(1.0, QColor("#1fb86b"))
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    p.fillPath(path, QBrush(grad))

    # jemné světlo nahoře
    hi = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.center().y()))
    hi.setColorAt(0.0, QColor(255, 255, 255, 60))
    hi.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(path, QBrush(hi))

    # zaškrtnutí (checkmark)
    pen = QPen(QColor("#ffffff"))
    pen.setWidthF(size * 0.11)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    check = QPainterPath()
    check.moveTo(size * 0.30, size * 0.52)
    check.lineTo(size * 0.44, size * 0.66)
    check.lineTo(size * 0.71, size * 0.34)
    p.drawPath(check)

    p.end()
    return pm


def make_app_icon() -> QIcon:
    icon = QIcon()
    for s in _SIZES:
        icon.addPixmap(_draw(s))
    return icon


def save_icon_files(directory) -> None:
    """Best-effort uložení PNG/ICO (pro zástupce). Selhání ignorujeme."""
    from pathlib import Path

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        _draw(256).save(str(directory / "icon.png"), "PNG")
    except Exception:
        pass
    try:
        _draw(256).save(str(directory / "icon.ico"), "ICO")
    except Exception:
        pass
