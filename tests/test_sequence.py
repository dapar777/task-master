"""Sekvence úkolů: řetěz blokování s potvrzením pořadí v dialogu.

Druhý úkol čeká na první, třetí na druhý atd. Dokončením se vždy odemkne
jen následující. Dialog umožní pořadí přeskládat nebo položku vyřadit.
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
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialogButtonBox,
    QMessageBox,
)

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_seq_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

from app.constants import APP_NAME, ORG_NAME  # noqa: E402

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

from app.mainwindow import MainWindow  # noqa: E402
from app.storage import Workspace  # noqa: E402
from app.taskdialog import SequenceDialog  # noqa: E402

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


ws = Workspace(tmp)
ws.load()
for t in ("Alfa", "Beta", "Gama", "Delta"):
    ws.create_root(t)
ws.load()

print("1) Dialog: číslování, přeuspořádání, vyřazení")
dlg = SequenceDialog(list(ws.roots))
titles = lambda: [dlg.list.item(i).text() for i in range(dlg.list.count())]  # noqa: E731
check("položky jsou očíslované", titles()[0].startswith("1."))
names_before = [t.split("  ", 1)[1] for t in titles()]
dlg.list.setCurrentRow(2)
dlg._move(-1)
names_after = [t.split("  ", 1)[1] for t in titles()]
expected = names_before[:1] + [names_before[2], names_before[1]] + names_before[3:]
check(f"posun nahoru přehodil pořadí ({names_after[:3]})",
      names_after == expected)
check("přečíslovalo se", titles()[1].startswith("2."))
dlg.list.setCurrentRow(0)
dlg._remove()
check("vyřazení ubralo položku", len(titles()) == 3)
ok_btn = dlg.buttons.button(QDialogButtonBox.StandardButton.Ok)
check("OK je povolené při 3 úkolech", ok_btn.isEnabled())
while dlg.list.count() > 1:
    dlg.list.setCurrentRow(0)
    dlg._remove()
check("OK je zakázané při jednom úkolu", not ok_btn.isEnabled())
check("shrnutí to vysvětlí", "aspoň dva" in dlg.summary.text())
dlg.close()

# dialog v dalších krocích potvrzuj beze změny pořadí
_orig_get = SequenceDialog.get
atexit.register(lambda: setattr(SequenceDialog, "get", _orig_get))
SequenceDialog.get = staticmethod(lambda parent, nodes: list(nodes))

_orig_box = {n: getattr(QMessageBox, n)
             for n in ("question", "warning", "information")}


def _restore_box():
    for n, fn in _orig_box.items():
        setattr(QMessageBox, n, fn)


atexit.register(_restore_box)
for _n in ("question", "warning", "information"):
    setattr(QMessageBox, _n,
            staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

win = MainWindow()
atexit.register(lambda: (win.close(), win.deleteLater()))
win.resize(1000, 650)
win.show()
QTest.qWaitForWindowExposed(win)
app.processEvents()


def node(t):
    return next(n for n in win.workspace.all_nodes() if n.title == t)


def st(t):
    return node(t).meta.get("_status")


def blocker_of(t):
    b = node(t).blocked_by
    if not b:
        return None
    return next((x.title for x in win.workspace.all_nodes() if x.task_id == b), None)


def select(names):
    nodes = [node(t) for t in names]
    win.card_view.select_paths([str(n.path) for n in nodes])
    win._current_node = nodes[0]
    app.processEvents()


def settle():
    app.processEvents()
    QTest.qWait(80)
    app.processEvents()


print("2) Vytvoření sekvence zřetězí označené úkoly")
select(["Alfa", "Beta", "Gama"])
win._make_sequence()
settle()
check("první zůstal volný", st("Alfa") == "todo")
check("druhý je blokovaný", st("Beta") == "blocked")
check("druhý čeká na první", blocker_of("Beta") == "Alfa")
check("třetí čeká na druhý", blocker_of("Gama") == "Beta")
check("neoznačený úkol se nezměnil", st("Delta") == "todo")

print("3) Undo vrátí celou sekvenci jedním krokem")
before = len(win.undo.entries)
win._undo()
settle()
check("Beta i Gama jsou zpět volné",
      st("Beta") == "todo" and st("Gama") == "todo")
check("stačil jeden záznam", before >= 1)

print("4) Sekvence se odemyká postupně")
select(["Alfa", "Beta", "Gama"])
win._make_sequence()
settle()
win._apply_status_to([node("Alfa")], "done")
settle()
check("dokončením prvního se odemkl druhý", st("Beta") == "todo")
check("třetí zůstává blokovaný", st("Gama") == "blocked")
win._apply_status_to([node("Beta")], "done")
settle()
check("dokončením druhého se odemkl třetí", st("Gama") == "todo")

print("5) Méně než dva úkoly sekvenci nevytvoří")
infos = {"n": 0}
QMessageBox.information = staticmethod(
    lambda *a, **k: infos.__setitem__("n", infos["n"] + 1))
win.card_view.select_paths([str(node("Delta").path)])
win._current_node = node("Delta")
app.processEvents()
win._make_sequence()
settle()
check("uživatel byl upozorněn", infos["n"] == 1)
check("Delta zůstala nedotčená", st("Delta") == "todo")

print("6) Funguje bez opuštění Bez rušení")
check("režim zůstal cards", win._view_mode == "cards")

print("7) Výchozí pořadí odpovídá tomu, co je vidět na obrazovce")
from app.tasktree import NODE_ROLE  # noqa: E402

# vlastní pořadí (Zebra, Alfa, Mango) se nesmí přepsat abecedním
par = win.workspace.create_root("Rodic")
for t in ("Zebra", "Alfa", "Mango"):
    win.workspace.create_child_of(par, t)
win.workspace.load()
win._populate()
app.processEvents()
all_nodes = list(win.workspace.all_nodes())


def tree_seen():
    out = []

    def walk(it):
        n = it.data(0, NODE_ROLE)
        if n is not None:
            out.append(n.title)
        for i in range(it.childCount()):
            walk(it.child(i))

    for i in range(win.tree.topLevelItemCount()):
        walk(win.tree.topLevelItem(i))
    return out


def cards_seen():
    by_path = {str(n.path): n.title for n in all_nodes}
    return [by_path[p] for p in win.card_view._order if p in by_path]


for mode in ("tree", "list", "cards"):
    win._view_mode = mode
    win._populate()
    app.processEvents()
    QTest.qWait(60)
    app.processEvents()
    seen = cards_seen() if mode == "cards" else tree_seen()
    order = [n.title for n in win._in_view_order(all_nodes)]
    check(f"{mode}: pořadí v dialogu = pořadí na obrazovce", seen == order)

print("8) Pořadí sleduje i přeskupení podle stavů (Bez rušení)")
win._view_mode = "cards"
node("Alfa").set_field("_status", "waiting")
win._populate()
app.processEvents()
QTest.qWait(60)
app.processEvents()
check("po změně stavu pořadí pořád sedí",
      cards_seen() == [n.title for n in win._in_view_order(all_nodes)])

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
