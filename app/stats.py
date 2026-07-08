"""Statistiky úkolů: založené/uzavřené za období, doba do uzavření.

Data se čtou z metadat: `_created` (vznik), `_completed` (přechod na „done"),
`_status`. Dialog kreslí jednoduché sloupcové grafy přes QPainter (bez
externích knihoven).
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .constants import STATUSES


def _parse_dt(s):
    try:
        return datetime.fromisoformat(s) if s else None
    except (ValueError, TypeError):
        return None


def _fmt_duration(hours: float) -> str:
    if hours < 1:
        return f"{int(round(hours * 60))} min"
    if hours < 48:
        return f"{hours:.1f} h"
    return f"{hours / 24:.1f} dní"


# hranice histogramu doby do uzavření (v hodinách) + popisky
_DUR_BUCKETS = [
    (1, "< 1 h"),
    (4, "1–4 h"),
    (24, "4–24 h"),
    (72, "1–3 dny"),
    (168, "3–7 dní"),
    (float("inf"), "> 7 dní"),
]


def compute_stats(nodes, days: int = 14, today: date | None = None) -> dict:
    """Spočítá statistiky ze seznamu uzlů."""
    nodes = list(nodes)
    today = today or date.today()

    by_status = Counter(n.meta.get("_status", "") for n in nodes)
    created_per_day: Counter = Counter()
    completed_per_day: Counter = Counter()
    durations: list[float] = []  # hodiny do uzavření

    for n in nodes:
        created = _parse_dt(n.meta.get("_created"))
        if created:
            created_per_day[created.date()] += 1
        completed = _parse_dt(n.meta.get("_completed"))
        if completed:
            completed_per_day[completed.date()] += 1
            if created and completed >= created:
                durations.append((completed - created).total_seconds() / 3600.0)

    day_list = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    created_series = [created_per_day.get(d, 0) for d in day_list]
    completed_series = [completed_per_day.get(d, 0) for d in day_list]

    def since(n_days):
        cutoff = today - timedelta(days=n_days - 1)
        cr = sum(v for d, v in created_per_day.items() if d >= cutoff)
        co = sum(v for d, v in completed_per_day.items() if d >= cutoff)
        return cr, co

    # histogram doby do uzavření
    dur_hist = [0] * len(_DUR_BUCKETS)
    for h in durations:
        for i, (hi, _) in enumerate(_DUR_BUCKETS):
            if h < hi:
                dur_hist[i] += 1
                break

    durations_sorted = sorted(durations)
    med = None
    if durations_sorted:
        m = len(durations_sorted) // 2
        med = (durations_sorted[m] if len(durations_sorted) % 2
               else (durations_sorted[m - 1] + durations_sorted[m]) / 2)

    return {
        "total": len(nodes),
        "by_status": by_status,
        "days": days,
        "day_labels": [d.strftime("%d.%m.") for d in day_list],
        "created_series": created_series,
        "completed_series": completed_series,
        "today_created": created_per_day.get(today, 0),
        "today_completed": completed_per_day.get(today, 0),
        "w_created": since(7)[0], "w_completed": since(7)[1],
        "p_created": since(days)[0], "p_completed": since(days)[1],
        "dur_hist": dur_hist,
        "dur_labels": [lbl for _, lbl in _DUR_BUCKETS],
        "dur_count": len(durations),
        "dur_avg": (sum(durations) / len(durations)) if durations else None,
        "dur_med": med,
        "dur_min": min(durations) if durations else None,
        "dur_max": max(durations) if durations else None,
    }


class _BarChart(QWidget):
    """Sloupcový graf: jedna nebo dvě série hodnot pod společnými popisky."""

    def __init__(self, labels, series, parent=None):
        # series: list[(name, "#rrggbb", [values])]
        super().__init__(parent)
        self._labels = labels
        self._series = series
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        left, right, top, bottom = 8, 8, 10, 34
        plot = QRectF(left, top, W - left - right, H - top - bottom)
        maxv = max([max(vals) for _, _, vals in self._series if vals] + [1])

        # osa
        p.setPen(QPen(QColor("#cccccc")))
        p.drawLine(plot.left(), plot.bottom(), plot.right(), plot.bottom())

        n = len(self._labels)
        if n == 0:
            return
        group_w = plot.width() / n
        ns = len(self._series)
        bar_w = min(group_w * 0.8 / ns, 26)
        small = QFont(self.font()); small.setPointSize(8)

        for i in range(n):
            gx = plot.left() + i * group_w + (group_w - bar_w * ns) / 2
            for s, (_, color, vals) in enumerate(self._series):
                v = vals[i] if i < len(vals) else 0
                bh = (v / maxv) * plot.height() if maxv else 0
                x = gx + s * bar_w
                rect = QRectF(x, plot.bottom() - bh, bar_w - 2, bh)
                p.fillRect(rect, QColor(color))
                if v:
                    p.setFont(small); p.setPen(QColor("#444"))
                    p.drawText(QRectF(x - 4, plot.bottom() - bh - 14, bar_w + 6, 12),
                               Qt.AlignmentFlag.AlignCenter, str(v))
            # popisek pod skupinou
            p.setFont(small); p.setPen(QColor("#666"))
            p.drawText(QRectF(plot.left() + i * group_w, plot.bottom() + 3, group_w, 14),
                       Qt.AlignmentFlag.AlignCenter, self._labels[i])
        p.end()


def _legend(series) -> QWidget:
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addStretch(1)
    for name, color, _ in series:
        sw = QLabel("■")
        sw.setStyleSheet(f"color:{color}; font-size:14px;")
        lab = QLabel(name)
        lay.addWidget(sw); lay.addWidget(lab)
        lay.addSpacing(10)
    lay.addStretch(1)
    return box


class StatsDialog(QDialog):
    def __init__(self, nodes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Statistiky")
        self.setMinimumWidth(560)
        s = compute_stats(nodes)

        layout = QVBoxLayout(self)

        # ---- souhrn ----
        summ = QGridLayout()
        summ.setHorizontalSpacing(18)

        def cell(r, c, title, value, color="#1c1c1c"):
            box = QVBoxLayout()
            v = QLabel(str(value)); v.setStyleSheet(f"font-size:20px; font-weight:bold; color:{color};")
            t = QLabel(title); t.setStyleSheet("color:#666; font-size:11px;")
            box.setSpacing(0); box.addWidget(v); box.addWidget(t)
            wrap = QWidget(); wrap.setLayout(box)
            summ.addWidget(wrap, r, c)

        st = s["by_status"]
        cell(0, 0, "Úkolů celkem", s["total"])
        cell(0, 1, STATUSES["done"], st.get("done", 0), "#2e9e4f")
        cell(0, 2, STATUSES["in_progress"], st.get("in_progress", 0), "#1a6fd6")
        cell(0, 3, STATUSES["todo"], st.get("todo", 0))
        cell(0, 4, STATUSES["blocked"], st.get("blocked", 0), "#c0392b")
        cell(1, 0, "Založené dnes", s["today_created"], "#4f7cff")
        cell(1, 1, "Uzavřené dnes", s["today_completed"], "#2e9e4f")
        cell(1, 2, "Založené 7 dní", s["w_created"], "#4f7cff")
        cell(1, 3, "Uzavřené 7 dní", s["w_completed"], "#2e9e4f")
        layout.addLayout(summ)

        layout.addWidget(_hline())

        # ---- graf založené vs uzavřené za období ----
        layout.addWidget(_section(f"Založené a uzavřené za posledních {s['days']} dní"))
        day_series = [
            ("Založené", "#4f7cff", s["created_series"]),
            ("Uzavřené", "#2e9e4f", s["completed_series"]),
        ]
        layout.addWidget(_BarChart(s["day_labels"], day_series))
        layout.addWidget(_legend(day_series))

        layout.addWidget(_hline())

        # ---- doba do uzavření ----
        layout.addWidget(_section("Doba do uzavření úkolu"))
        if s["dur_count"]:
            info = (f"Uzavřeno: {s['dur_count']}   ·   průměr: {_fmt_duration(s['dur_avg'])}"
                    f"   ·   medián: {_fmt_duration(s['dur_med'])}"
                    f"   ·   nejrychleji: {_fmt_duration(s['dur_min'])}"
                    f"   ·   nejdéle: {_fmt_duration(s['dur_max'])}")
            lab = QLabel(info); lab.setStyleSheet("color:#444; font-size:11px;"); lab.setWordWrap(True)
            layout.addWidget(lab)
            dur_series = [("Počet úkolů", "#e08a1e", s["dur_hist"])]
            layout.addWidget(_BarChart(s["dur_labels"], dur_series))
        else:
            empty = QLabel("Zatím žádné uzavřené úkoly s časem vzniku i dokončení.")
            empty.setStyleSheet("color:#999;")
            layout.addWidget(empty)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


def _hline() -> QFrame:
    ln = QFrame(); ln.setFrameShape(QFrame.Shape.HLine); ln.setStyleSheet("color:#e0e0e0;")
    return ln


def _section(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setStyleSheet("font-weight:600; color:#333; margin-top:4px;")
    return lab
