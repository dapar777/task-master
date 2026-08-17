"""Zablokování sourozenců (i s jejich podúkoly) vybraným úkolem.

Pravidla: blokují se sourozenci a celé jejich podstromy; vybraný úkol ani
jeho vlastní podstrom se nemění; hotové i už blokované úkoly se přeskakují.
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
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_block_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

# MainWindow si dělá QSettings(ORG_NAME, APP_NAME) natvrdo – přesměruj
# workspace do dočasného adresáře a původní hodnoty vrať (viz README).
from app.constants import APP_NAME, ORG_NAME  # noqa: E402

_s = QSettings(ORG_NAME, APP_NAME)
_orig = {k: _s.value(k) for k in ("workspace", "view_mode")}


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
_s.setValue("view_mode", "tree")
_s.sync()

from app.mainwindow import MainWindow  # noqa: E402
from app.storage import Workspace  # noqa: E402

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


# --- data ---------------------------------------------------------------
# Rodic
#   A  (vybraný)      + podúkol A1
#   B                 + podúkoly B1, B2
#   C  (hotový)
#   D  (blokovaný jiným úkolem)
# Solo (kořenový sourozenec Rodice)
ws = Workspace(tmp)
ws.load()
par = ws.create_root("Rodic")
a = par.create_child("A")
a.create_child("A1")
b = par.create_child("B")
b.create_child("B1")
b.create_child("B2")
c = par.create_child("C")
d = par.create_child("D")
other = ws.create_root("Jiny blokujici")
ws.load()

# C hotový, D blokovaný někým jiným
node = lambda t: next(n for n in ws.all_nodes() if n.title == t)  # noqa: E731
node("C").set_field("_status", "done")
node("D").set_field("_status", "blocked")
node("D").set_blocked_by(node("Jiny blokujici").task_id)
ws.load()

win = MainWindow()
win.workspace = ws
win.tree.resolver = ws.node_by_id
win._view_mode = "tree"
win._populate()

# dialog vždy potvrď
_q = QMessageBox.question
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)


def st(t):
    return node(t).meta.get("_status")


try:
    print("1) Zablokování sourozenců úkolem 'A'")
    a = node("A")
    win._current_node = a
    win._block_siblings()
    aid = a.task_id

    check("B je blokované", st("B") == "blocked")
    check("B ukazuje na A", node("B").blocked_by == aid)
    check("podúkol B1 je blokovaný (podstrom sourozence)", st("B1") == "blocked")
    check("podúkol B2 je blokovaný", st("B2") == "blocked")
    check("B1 ukazuje na A", node("B1").blocked_by == aid)

    print("2) Výjimky")
    check("hotové 'C' zůstalo hotové", st("C") == "done")
    check("už blokované 'D' si drží původní blokující",
          node("D").blocked_by == node("Jiny blokujici").task_id)

    print("3) Vybraný úkol a jeho podstrom se nemění")
    check("'A' se nezablokovalo samo", st("A") != "blocked")
    check("podúkol 'A1' zůstal nedotčený", st("A1") != "blocked")

    print("4) Nadřazený 'Rodic' není sourozenec – nedotčen")
    check("'Rodic' není blokovaný", st("Rodic") != "blocked")

    print("5) Undo vrátí stav zpět")
    win._undo()
    check("B je zpět nezablokované", st("B") != "blocked")
    check("B1 je zpět nezablokovaný", st("B1") != "blocked")

    print("6) Kořenová úroveň má sourozence taky")
    root_sel = node("Rodic")
    win._current_node = root_sel
    win._block_siblings()
    check("kořenový sourozenec 'Jiny blokujici' je blokovaný",
          st("Jiny blokujici") == "blocked")
    check("'Jiny blokujici' ukazuje na 'Rodic'",
          node("Jiny blokujici").blocked_by == root_sel.task_id)
    check("podúkoly vybraného kořene zůstaly nedotčené", st("A") != "blocked")

    print("7) Dokončením blokujícího se vše odblokuje")
    win._undo()  # vrať krok 6
    fresh = Workspace(tmp)
    fresh.load()
    win.workspace = fresh
    win.tree.resolver = fresh.node_by_id
    win._populate()
    node = lambda t: next(n for n in fresh.all_nodes() if n.title == t)  # noqa: E731
    sel = node("A")
    win._current_node = sel
    win._block_siblings()
    check("B zablokované před dokončením", node("B").meta.get("_status") == "blocked")
    win._apply_status_to([node("A")], "done")
    app.processEvents()
    check("dokončením 'A' se 'B' odblokovalo",
          node("B").meta.get("_status") == "todo")
    check("odblokoval se i podúkol 'B1'",
          node("B1").meta.get("_status") == "todo")
    ws = fresh  # další kroky pracují nad aktuálním workspace

    print("8) Hotovým úkolem blokovat nelze")
    warned = {"n": 0}
    _w = QMessageBox.warning
    QMessageBox.warning = staticmethod(
        lambda *a, **k: warned.__setitem__("n", warned["n"] + 1))
    try:
        win._undo()  # vrať krok 6
        done_node = node("C")  # hotový
        win._current_node = done_node
        before = {n.title: n.meta.get("_status") for n in ws.all_nodes()}
        win._block_siblings()
        after = {n.title: n.meta.get("_status") for n in ws.all_nodes()}
        check("hotový úkol nic nezablokoval", before == after)
        check("uživatel byl upozorněn", warned["n"] == 1)
    finally:
        QMessageBox.warning = _w
finally:
    QMessageBox.question = _q

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
win.close()
sys.exit(1 if fails else 0)
