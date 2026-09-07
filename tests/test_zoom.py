"""Zoom celého UI a přepínač tématu v hlavičce.

Hlídá, že jeden faktor v theme prostoupí QSS, písma i rozměry mimo QSS
(karty, strom, hlavička), že se zoom drží v nastavení a že tlačítko
v hlavičce přepíná téma stejně jako akce v menu."""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QKeySequence, QShortcut, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_zoom_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

from app.constants import APP_NAME, ORG_NAME  # noqa: E402

_s = QSettings(ORG_NAME, APP_NAME)
_orig = {k: _s.value(k) for k in ("workspace", "view_mode", "theme", "zoom")}


def _restore_settings():
    s = QSettings(ORG_NAME, APP_NAME)
    for k, v in _orig.items():
        if v is None:
            s.remove(k)
        else:
            s.setValue(k, v)
    s.sync()


atexit.register(_restore_settings)
_s.setValue("workspace", str(tmp))
_s.setValue("view_mode", "cards")
_s.setValue("theme", "light")
_s.remove("zoom")
_s.sync()

from app import theme  # noqa: E402
from app.storage import Workspace  # noqa: E402
from app.widgets import Chip, TitleLabel  # noqa: E402

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


# --- 1) čistá aritmetika zoomu ---
print("1) px / pt / scaled")
theme.apply(app, "light", zoom=1.0)
check("px(8) při 100 % = 8", theme.px(8) == 8)
check("scaled() při 100 % nemění text", theme.scaled("padding: 1.5px 7px; font-size: 8pt;") == "padding: 1.5px 7px; font-size: 8pt;")
theme.set_zoom(1.5)
check("px(8) při 150 % = 12", theme.px(8) == 12)
check("px(-7) zachová znaménko", theme.px(-7) == -10 or theme.px(-7) == -11)
check("px(0) = 0", theme.px(0) == 0)
check("pt(10) při 150 % = 15.0", theme.pt(10) == 15.0)
out = theme.scaled("padding: 6px 28px; border: 1px solid #000; font-size: 8pt; margin: -7px;")
check("scaled(): px se násobí, 1px hranice zůstává, pt se násobí, záporné hodnoty přežijí",
      out == "padding: 9px 42px; border: 1px solid #000; font-size: 12pt; margin: -10px;" or
      out == "padding: 9px 42px; border: 1px solid #000; font-size: 12pt; margin: -11px;")
check("set_zoom ořízne na meze", theme.set_zoom(9) == theme.ZOOM_MAX and theme.set_zoom(0.1) == theme.ZOOM_MIN)
check("set_zoom snese nesmysl", theme.set_zoom("x") == 1.0)
check("chip_qss prochází zoomem", "padding:1px 7px" in theme.chip_qss("#000000", "#ffffff"))

# --- 2) apply(): písmo aplikace a QSS ---
print("2) apply() se zoomem")
theme.apply(app, "light", zoom=2.0)
check("písmo aplikace je 20 pt", abs(app.font().pointSizeF() - 20.0) < 0.01)
check("QSS je přeškálovaný (QMenu::item padding 12px)", "QMenu::item { padding: 12px 56px 12px 20px" in app.styleSheet())
check("title_font jde přes zoom", abs(theme.title_font(14).pointSizeF() - 28.0) < 0.01)
theme.apply(app, "dark")
check("apply bez zoomu drží předchozí faktor", theme.zoom() == 2.0 and theme.is_dark())
theme.apply(app, "light", zoom=1.0)
check("zpět na 100 %", theme.zoom() == 1.0 and abs(app.font().pointSizeF() - 10.0) < 0.01)

# --- 3) widgety mimo QSS reagují na retheme ---
print("3) Widgety")
title = TitleLabel("Připravit podklady", 14.5)
h1 = title.sizeHint().height()
theme.apply(app, "light", zoom=1.5)
title.retheme()
check("TitleLabel po zoomu vyšší", title.sizeHint().height() > h1)
chip = Chip("Probíhá", "#000000", "#ffffff", icon="clock")
chip.retheme()
check("Chip má po zoomu ikonu 18 px", 'width="18" height="18"' in chip.text())
theme.apply(app, "light", zoom=1.0)

# --- 4) hlavní okno: zkratky, kolečko, nastavení, popisek, karty, strom ---
print("4) Hlavní okno")
ws = Workspace(tmp)
ws.load()
r = ws.create_root("Projekt")
a = ws.create_child_of(r, "Úkol A")
a.meta.update({"_status": "in_progress", "_priority": 7})
a.save_meta()
ws.create_child_of(r, "Úkol B")

from app.mainwindow import MainWindow  # noqa: E402

win = MainWindow()
win.resize(1200, 760)
win.show()
app.processEvents()
check("start bez uloženého zoomu = 100 %, popisek skrytý", theme.zoom() == 1.0 and not win.zoom_label.isVisible())
check("karty mají otisk se zoomem", all(s[-1] == 1.0 for s in win.card_view._stamps.values()) and win.card_view._stamps)
h_card = next(iter(win.card_view._cards.values())).sizeHint().height()
col_w = win.card_view.column.maximumWidth()

win.act["view.zoom_in"].trigger()
app.processEvents()
check("Ctrl++ zvětší na 110 %", abs(theme.zoom() - 1.1) < 1e-6)
check("popisek ve stavovém řádku ukazuje 110 %", win.zoom_label.text() == "110 %" and win.zoom_label.isVisible())
check("zoom se uložil do nastavení", abs(float(QSettings(ORG_NAME, APP_NAME).value("zoom")) - 1.1) < 1e-6)
check("otisk karet se změnil (karty se přestavěly)", all(abs(s[-1] - 1.1) < 1e-6 for s in win.card_view._stamps.values()))
check("karta je vyšší", next(iter(win.card_view._cards.values())).sizeHint().height() > h_card)
check("sloupec karet je širší", win.card_view.column.maximumWidth() > col_w)

# rychlé kroky za sebou se slévají (throttling), výsledek je ale správný
for _ in range(3):
    win.act["view.zoom_in"].trigger()
win._zoom_timer.stop()
win._flush_zoom()
app.processEvents()
check("tři rychlé kroky = 140 %", abs(theme.zoom() - 1.4) < 1e-6)
check("písmo aplikace 14 pt", abs(app.font().pointSizeF() - 14.0) < 0.01)

win._set_view_mode("tree")
app.processEvents()
check("strom má odsazení podle zoomu", win.tree.indentation() == theme.px(18))
check("řádek stromu je vyšší než 30 px", win.tree.sizeHintForRow(0) >= theme.px(30) > 30)

win.act["view.zoom_out"].trigger()
# krok během okna slévání zůstane čekat; časovač ho pak provede (tady ručně)
check("krok během slévání čeká", win._zoom_pending is not None and abs(theme.zoom() - 1.4) < 1e-6)
win._zoom_timer.stop()
win._flush_zoom()
app.processEvents()
check("Ctrl+- zmenší na 130 %", abs(theme.zoom() - 1.3) < 1e-6)

# Ctrl+kolečko nad libovolným widgetem (globální filtr)
ev = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, -120),
                 Qt.MouseButton.NoButton, Qt.KeyboardModifier.ControlModifier,
                 Qt.ScrollPhase.NoScrollPhase, False)
handled = app.sendEvent(win.tree.viewport(), ev)
win._zoom_timer.stop()
win._flush_zoom()
app.processEvents()
check("Ctrl+kolečko dolů oddálí na 120 %", abs(theme.zoom() - 1.2) < 1e-6)
ev2 = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, 120),
                  Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                  Qt.ScrollPhase.NoScrollPhase, False)
app.sendEvent(win.tree.viewport(), ev2)
app.processEvents()
check("kolečko bez Ctrl zoom nemění", abs(theme.zoom() - 1.2) < 1e-6)

win.act["view.zoom_reset"].trigger()
app.processEvents()
check("Ctrl+0 vrátí 100 % a skryje popisek", theme.zoom() == 1.0 and not win.zoom_label.isVisible())
check("výchozí zkratky", win.shortcuts.default("view.zoom_in") == "Ctrl++"
      and win.shortcuts.default("view.zoom_out") == "Ctrl+-" and win.shortcuts.default("view.zoom_reset") == "Ctrl+0")
check("zkratky nekolidují", not any("view.zoom" in ids for ids in win.shortcuts.conflicts().values()))
m_view = next(m for m in win.menuBar().findChildren(QMenu) if m.title() == "&Zobrazení")
check("zoom je v menu Zobrazení",
      all(win.act[c] in m_view.actions() for c in ("view.zoom_in", "view.zoom_out", "view.zoom_reset")))
check("Ctrl+= je doplňková zkratka přiblížení",
      any(sc.key() == QKeySequence("Ctrl+=") for sc in win.findChildren(QShortcut)))

# --- 5) přepínač tématu v hlavičce ---
print("5) Tlačítko tématu v hlavičce")
check("ve světlém tématu ukazuje měsíc", win.theme_btn._icon_name == "moon" and "tmavé" in win.theme_btn.toolTip())
win.theme_btn.click()
app.processEvents()
check("klik přepne na tmavé téma", theme.is_dark())
check("akce v menu je zaškrtnutá", win.act["view.dark_theme"].isChecked())
check("v tmavém ukazuje slunce", win.theme_btn._icon_name == "sun" and "světlé" in win.theme_btn.toolTip())
check("volba se uložila", QSettings(ORG_NAME, APP_NAME).value("theme") == "dark")
win.theme_btn.click()
app.processEvents()
check("druhý klik vrátí světlé", not theme.is_dark() and win.theme_btn._icon_name == "moon")
check("přepnutí tématu zoom nemění", theme.zoom() == 1.0)

# --- 6) start s uloženým zoomem (jako main.py) ---
print("6) Uložený zoom")
win.close()
theme.apply(app, "light", zoom=float(QSettings(ORG_NAME, APP_NAME).value("zoom", 1.0)))
check("po resetu se ukládá 1.0", theme.zoom() == 1.0)
_s.setValue("zoom", 1.3)
theme.apply(app, "light", zoom=_s.value("zoom", 1.0, type=float))
win2 = MainWindow()
win2.show()
app.processEvents()
check("okno startuje se 130 % a popiskem", abs(theme.zoom() - 1.3) < 1e-6 and win2.zoom_label.text() == "130 %")
win2.close()
theme.apply(app, "light", zoom=1.0)

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
