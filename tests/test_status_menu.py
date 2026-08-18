"""Stav lze nastavit z kontextového menu, i v režimu Bez rušení.

V kartách není vidět combobox stavu z detailu, takže „Čeká" a „Blokováno"
nešlo nastavit bez přepnutí do stromu. Podnabídka „Stav" to řeší v obou
zobrazeních a respektuje vícenásobný výběr.
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_stmenu_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

from app.constants import APP_NAME, ORG_NAME, STATUSES  # noqa: E402

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

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


ws = Workspace(tmp)
ws.load()
for t in ("Alfa", "Beta", "Gama"):
    ws.create_root(t)
ws.load()

# dialogy zastínit a vrátit – jinak test čeká na kliknutí
_orig_box = {n: getattr(QMessageBox, n)
             for n in ("question", "warning", "information")}
_orig_blocker = mw.BlockerDialog.get


def _restore_dialogs():
    for n, fn in _orig_box.items():
        setattr(QMessageBox, n, fn)
    mw.BlockerDialog.get = _orig_blocker


atexit.register(_restore_dialogs)
for _n in ("question", "warning", "information"):
    setattr(QMessageBox, _n,
            staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
# „bez vazby" – dialog výběru blokujícího úkolu neotvírej
mw.BlockerDialog.get = staticmethod(lambda *a, **k: "")

win = MainWindow()
atexit.register(lambda: (win.close(), win.deleteLater()))
win.resize(1000, 650)
win.show()
QTest.qWaitForWindowExposed(win)
app.processEvents()


def node(t):
    return next(n for n in win.workspace.all_nodes() if n.title == t)


def status_menu(n):
    menu = win._build_card_menu(n)
    return next((a.menu() for a in menu.actions()
                 if a.menu() and a.menu().title() == "Stav"), None)


print("1) Podnabídka Stav je v menu karty a nabízí všechny stavy")
check("režim je Bez rušení", win._view_mode == "cards")
sm = status_menu(node("Alfa"))
check("podnabídka Stav existuje", sm is not None)
labels = [a.text() for a in sm.actions()]
check("nabízí všech 5 stavů", sorted(labels) == sorted(STATUSES.values()))
check("aktuální stav je zaškrtnutý",
      [a.text() for a in sm.actions() if a.isChecked()] == [STATUSES["todo"]])

print("2) „Čeká\" jde nastavit bez opuštění Bez rušení")
win._set_status_from_card(node("Alfa"), "waiting")
app.processEvents()
QTest.qWait(60)
app.processEvents()
check("stav je waiting", node("Alfa").meta.get("_status") == "waiting")
check("zůstali jsme v kartách", win._view_mode == "cards")

print("3) „Blokováno\" taky (dotaz na blokující úkol proběhne)")
win._set_status_from_card(node("Beta"), "blocked")
app.processEvents()
QTest.qWait(80)
app.processEvents()
check("stav je blocked", node("Beta").meta.get("_status") == "blocked")
check("zůstali jsme v kartách", win._view_mode == "cards")

print("4) Volba beze změny nic nedělá")
before = node("Gama").meta.get("_status")
win._set_status_from_card(node("Gama"), before)
app.processEvents()
check("stav se nezměnil", node("Gama").meta.get("_status") == before)

print("5) Zaškrtnutí sleduje aktuální stav")
sm = status_menu(node("Alfa"))
check("zaškrtnuto je Čeká",
      [a.text() for a in sm.actions() if a.isChecked()] == [STATUSES["waiting"]])

print("6) Podnabídka je i v kontextovém menu stromu")
win._view_mode = "tree"
win._populate()
app.processEvents()
win._current_node = node("Gama")
sub = win._build_status_menu(node("Gama"), None)
check("podnabídka jde sestavit i pro strom", sub is not None)
check("má všech 5 stavů", len(sub.actions()) == len(STATUSES))

print("7) Podnabídka Stav je i v hlavním menu Úkol")
# hlavní menu se staví jednou při startu, položky se plní až při rozbalení
win._current_node = node("Gama")
win._m_status.aboutToShow.emit()
app.processEvents()
main_labels = [a.text() for a in win._m_status.actions()]
check("hlavní menu nabízí všech 5 stavů",
      sorted(main_labels) == sorted(STATUSES.values()))
check("zaškrtnutý je aktuální stav Gamy",
      [a.text() for a in win._m_status.actions() if a.isChecked()]
      == [STATUSES[node("Gama").meta.get("_status")]])

win._set_status_from_card(node("Gama"), "in_progress")
app.processEvents()
QTest.qWait(60)
app.processEvents()
win._current_node = node("Gama")
win._m_status.aboutToShow.emit()
app.processEvents()
check("zaškrtnutí sleduje změnu stavu",
      [a.text() for a in win._m_status.actions() if a.isChecked()]
      == [STATUSES["in_progress"]])

win._current_node = None
win._m_status.aboutToShow.emit()
app.processEvents()
acts = win._m_status.actions()
check("bez vybraného úkolu je položka zašedlá",
      len(acts) == 1 and not acts[0].isEnabled())

print("8) Stavy jsou i příkazy (paleta, volitelná zkratka)")
from app.shortcuts import COMMAND_DEFS  # noqa: E402

cmds = [c for c in COMMAND_DEFS if c.startswith("task.status_")]
check("existují 4 stavové příkazy", len(cmds) == 4)
check("všechny jsou zaregistrované v okně",
      all(c in win.act for c in cmds))
check("mají prázdnou výchozí zkratku (bez kolizí)",
      all(COMMAND_DEFS[c][2] == "" for c in cmds))

win._view_mode = "cards"
win._populate()
app.processEvents()
win._current_node = node("Alfa")
win.act["task.status_in_progress"].trigger()
app.processEvents()
QTest.qWait(60)
app.processEvents()
check("příkaz nastavil stav",
      node("Alfa").meta.get("_status") == "in_progress")

win._current_node = None
try:
    win.act["task.status_todo"].trigger()
    app.processEvents()
    check("bez vybraného úkolu příkaz nespadne", True)
except Exception as e:  # noqa: BLE001
    check(f"bez vybraného úkolu nespadne ({type(e).__name__})", False)

print("9) Přechod na Blokováno = jeden undo záznam")
# _apply_status_to zálohuje metadata a _ask_blocker to dělal znovu – jedno
# Ctrl+Z pak jen zrušilo vazbu a stav zůstal, takže bylo potřeba mačkat víc
win._view_mode = "cards"
win._populate()
app.processEvents()
target = node("Beta")
win._set_status_from_card(target, "todo")
app.processEvents()
QTest.qWait(60)
app.processEvents()
before_entries = len(win.undo.entries)
win._set_status_from_card(target, "blocked")
app.processEvents()
QTest.qWait(80)
app.processEvents()
check("stav je blocked", node("Beta").meta.get("_status") == "blocked")
check(f"přibyl právě jeden undo záznam "
      f"({len(win.undo.entries) - before_entries})",
      len(win.undo.entries) - before_entries == 1)
win._undo()
app.processEvents()
check("jedno Ctrl+Z vrátí stav zpět",
      node("Beta").meta.get("_status") == "todo")

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
