"""Stav „Čeká do…" – odklad s odpočtem, obnovení a řazení v Bez rušení.

Interval se volí v dialogu s posuvníky (předvyplněný naposledy použitou
hodnotou, poprvé z DEFAULT_SNOOZE). Dokud odpočet běží, úkol patří mezi
čekající; jakmile doběhne, jde úplně nahoru a nabídne tlačítko Obnovit.
"""
import atexit
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialogButtonBox,
    QMessageBox,
)

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_snooze_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

from app.constants import (  # noqa: E402
    APP_NAME,
    DEFAULT_SNOOZE,
    ELAPSED_GROUP_INDEX,
    ORG_NAME,
    STATUSES,
)

_s = QSettings(ORG_NAME, APP_NAME)
_orig = {k: _s.value(k) for k in ("workspace", "view_mode")}


def _restore():
    s = QSettings(ORG_NAME, APP_NAME)
    for k, v in _orig.items():
        if v is None:
            s.remove(k)
        else:
            s.setValue(k, v)
    s.sync()


atexit.register(_restore)
_s.setValue("workspace", str(tmp))
_s.setValue("view_mode", "cards")
_s.sync()

import app.mainwindow as mw  # noqa: E402
from app.mainwindow import MainWindow  # noqa: E402
from app.storage import Workspace  # noqa: E402
from app.taskdialog import SnoozeDialog, format_duration  # noqa: E402
from app.tasktree import _status_text  # noqa: E402

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


print("1) Datový model odkladu")
ws = Workspace(tmp)
ws.load()
for t in ("Akt", "Odloz", "Ceka1", "Ceka2", "Blok", "Hotov"):
    ws.create_root(t)
ws.load()
probe = next(n for n in ws.roots if n.title == "Odloz")
check("neodložený úkol nemá termín", probe.snooze_until is None)
probe.set_snooze(3600)
check("stav je snoozed", probe.meta.get("_status") == "snoozed")
check("zbývá skoro hodina", 3500 < probe.snooze_remaining() <= 3600)
check("odklad ještě neběžel naprázdno", not probe.snooze_elapsed())
check("délka se pamatuje pro Obnovit", probe.snooze_secs == 3600)
probe.set_field("_status", "todo")
probe.clear_snooze()
check("jiný stav odpočet ruší", probe.snooze_until is None)
check("délka zůstala k dispozici", probe.snooze_secs == 3600)

print("2) Formátování délky")
check("10 minut", format_duration(600) == "10 min")
check("1 h 30 min", format_duration(5400) == "1 h 30 min")
check("2 dny", format_duration(172800) == "2 d")

print("3) Dialog: posuvníky a výchozí hodnota")
dlg = SnoozeDialog()
check(f"předvyplněno z konfigurace {DEFAULT_SNOOZE}", dlg.parts() == DEFAULT_SNOOZE)
dlg._sliders["days"].setValue(1)
dlg._sliders["hours"].setValue(2)
dlg._sliders["minutes"].setValue(30)
check("posuvníky dávají správný počet sekund", dlg.seconds() == 95400)
ok_btn = dlg.buttons.button(QDialogButtonBox.StandardButton.Ok)
for key in ("days", "hours", "minutes"):
    dlg._sliders[key].setValue(0)
check("nulový interval je zakázaný", not ok_btn.isEnabled())
dlg.close()

print("4) Přechod na „Čeká do…\" přes aplikaci")
for _n in ("question", "warning", "information"):
    setattr(QMessageBox, _n,
            staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
_orig_get = SnoozeDialog.get
atexit.register(lambda: setattr(SnoozeDialog, "get", _orig_get))
mw.SnoozeDialog.get = staticmethod(lambda *a, **k: 2)  # 2 s, ať test nečeká

win = MainWindow()
atexit.register(lambda: (win.close(), win.deleteLater()))
win.resize(1000, 650)
win.show()
QTest.qWaitForWindowExposed(win)
app.processEvents()


def node(t):
    return next(n for n in win.workspace.all_nodes() if n.title == t)


def order():
    by_path = {str(n.path): n.title for n in win.workspace.all_nodes()}
    return [by_path[p] for p in win.card_view._order if p in by_path]


def settle():
    app.processEvents()
    QTest.qWait(90)
    app.processEvents()


for t, stat in (("Ceka1", "waiting"), ("Ceka2", "waiting"),
                ("Blok", "blocked"), ("Hotov", "done")):
    node(t).set_field(stat and "_status", stat)
win._populate()
settle()

win._current_node = node("Odloz")
win._apply_status_to([node("Odloz")], "snoozed")
settle()
check("úkol je odložený", node("Odloz").meta.get("_status") == "snoozed")
check("má běžící odpočet", not node("Odloz").snooze_elapsed())
check("stav má vlastní popisek", STATUSES["snoozed"] == "Čeká do…")

print("5) Běžící odklad je mezi čekajícími")
check(f"skupina = waiting ({win._group_index(node('Odloz'))})",
      win._group_index(node("Odloz")) == win._group_index(node("Ceka1")))
seq = order()
check("stojí mezi čekajícími, ne nahoře", seq[0] != "Odloz")

print("6) Karta ukazuje odpočet i tlačítko Obnovit")
card = win.card_view._cards.get(str(node("Odloz").path))
check("karta má odpočet", card is not None and card.countdown is not None)
check("karta má tlačítko Obnovit", card is not None and card.resume_btn is not None)
check("odpočet ukazuje zbývající čas", "⏳" in card.countdown.text())
check("strom ukazuje odpočet taky", "⏳" in _status_text(node("Odloz")))

print("7) Po doběhnutí jde úkol úplně nahoru")
time.sleep(2.2)
win._tick_snooze()
settle()
check("odklad doběhl", node("Odloz").snooze_elapsed())
check(f"skupina = elapsed ({ELAPSED_GROUP_INDEX})",
      win._group_index(node("Odloz")) == ELAPSED_GROUP_INDEX)
check(f"je první v pořadí ({order()[:2]})", order()[0] == "Odloz")
card = win.card_view._cards.get(str(node("Odloz").path))
check("karta hlásí vypršení", card is not None and "vypršelo" in card.countdown.text())
check("strom hlásí vypršení", "vypršel" in _status_text(node("Odloz")))

print("8) Obnovit spustí stejný interval znovu")
win._resume_snoozed(node("Odloz"))
settle()
check("odpočet zase běží", not node("Odloz").snooze_elapsed())
check("použil se stejný interval", node("Odloz").snooze_secs == 2)
check("úkol se vrátil mezi čekající",
      win._group_index(node("Odloz")) != ELAPSED_GROUP_INDEX)

print("9) Poslední interval se pamatuje pro příště")
mw.SnoozeDialog.get = staticmethod(lambda *a, **k: 5400)  # 1 h 30 min
win._current_node = node("Akt")
win._apply_status_to([node("Akt")], "snoozed")
settle()
check("zapamatováno jako (0, 1, 30)", win._last_snooze == (0, 1, 30))
check("uloženo i do nastavení",
      int(win.settings.value("snooze_h", 0)) == 1
      and int(win.settings.value("snooze_m", 0)) == 30)

print("10) Jiný stav odklad zruší")
win._apply_status_to([node("Akt")], "todo")
settle()
check("termín je pryč", node("Akt").snooze_until is None)
check("stav je todo", node("Akt").meta.get("_status") == "todo")

print("11) Undo vrátí odklad zpět")
before = node("Ceka1").meta.get("_status")
win._current_node = node("Ceka1")
win._apply_status_to([node("Ceka1")], "snoozed")
settle()
check("úkol byl odložen", node("Ceka1").meta.get("_status") == "snoozed")
win._undo()
settle()
check("undo vrátilo původní stav", node("Ceka1").meta.get("_status") == before)

print("12) Stav bez termínu (combobox v dialogu úkolu) neuvázne")
# „Čeká do…" jde vybrat i comboboxem, kde se na interval nikdo nezeptá –
# takový úkol nesmí zůstat viset s nefunkčním odpočtem
lost = node("Ceka2")
lost.set_field("_status", "snoozed")
lost.clear_snooze()
win._populate()
settle()
check("bez termínu se počítá jako doběhlý", lost.snooze_elapsed())
check("řadí se nahoru mezi doběhlé",
      win._group_index(lost) == ELAPSED_GROUP_INDEX)
card = win.card_view._cards.get(str(lost.path))
check("karta to říká místo prázdného odznaku",
      card is not None and "bez termínu" in card.countdown.text())
check("strom to říká taky", "bez termínu" in _status_text(lost))
check("nabídne tlačítko Obnovit",
      card is not None and card.resume_btn is not None)
win._resume_snoozed(lost)
settle()
check("Obnovit mu dá termín z poslední volby uživatele",
      lost.snooze_until is not None and not lost.snooze_elapsed())

print("13) Nový stav je i ve filtru")
from app.filterpanel import FilterPanel  # noqa: E402

fp = FilterPanel()
labels = [fp.status_box.itemText(i) for i in range(fp.status_box.count())]
check("filtr nabízí „Čeká do…“", STATUSES["snoozed"] in labels)
fp.status_box.set_checked_data(["snoozed"])
check("filtruje odložené", fp.matches(node("Odloz")))
check("nepustí běžné úkoly", not fp.matches(node("Hotov")))
fp.close()

print("14) Odpočet přežije restart aplikace")
# termín se ukládá absolutně do YAML, ne jako zbývající čas
fresh_ws = Workspace(tmp)
fresh_ws.load()
again = next((n for n in fresh_ws.all_nodes()
              if n.title == "Odloz"), None)
check("úkol je po načtení z disku pořád odložený",
      again is not None and again.meta.get("_status") == "snoozed")
check("termín zůstal zachovaný",
      again is not None and again.snooze_until is not None)
check("délka pro Obnovit zůstala",
      again is not None and again.snooze_secs > 0)

print("15) Odklad doběhlý za vypnuté aplikace je po startu nahoře")
from datetime import datetime as _dt, timedelta as _td  # noqa: E402

past = node("Blok")
past.meta["_status"] = "snoozed"
past.meta["_snooze_until"] = (_dt.now() - _td(days=1)).isoformat(timespec="seconds")
past.meta["_snooze_secs"] = 3600
past.save_meta()
win._populate()
settle()
check("termín v minulosti = doběhlý", past.snooze_elapsed())
check("řadí se mezi doběhlé nahoru",
      win._group_index(past) == ELAPSED_GROUP_INDEX)

print("16) Barva: odklad vypadá jako čekající, i po doběhnutí")
from app.constants import STATUS_COLORS, status_color  # noqa: E402
from app.cardview import _props_text  # noqa: E402

running = node("Ceka1")
running.set_snooze(3600)
elapsed = node("Odloz")
check("běžící odklad má barvu čekajícího",
      status_color(running) == STATUS_COLORS["waiting"])
check("nemá barvu blokovaného",
      status_color(running) != STATUS_COLORS["blocked"])
elapsed.set_snooze(1)
time.sleep(1.2)
check("doběhlý si barvu ponechá (nemění se)",
      status_color(elapsed) == STATUS_COLORS["waiting"])
check("že vypršel, říká text – ne barva",
      "vypršel" in _status_text(elapsed) and "vypršel" in _props_text(elapsed))
check("doběhlý už netvrdí, že čeká",
      STATUSES["snoozed"] not in _status_text(elapsed))

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
