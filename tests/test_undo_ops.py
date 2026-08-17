"""Undo pro strukturální operace bez kopírování celého workspace.

Přejmenování a přesun se zaznamenávají jako „moved" (jen cesty), mazání
jako „deleted" (záloha jen mazaných podstromů). Dřív se pro všechny dělal
snapshot celého workspace, což při stovkách úkolů trvalo sekundy.
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

tmp = Path(tempfile.mkdtemp(prefix="tm_undoops_"))
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
_s.setValue("view_mode", "tree")
_s.sync()

from app.mainwindow import MainWindow  # noqa: E402
from app.storage import Workspace  # noqa: E402

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


ws = Workspace(tmp)
ws.load()
alfa = ws.create_root("Alfa")
ws.create_child_of(alfa, "Alfa sub")
ws.create_root("Beta")
ws.create_root("Gama")
ws.load()

_orig_q = QMessageBox.question
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
atexit.register(lambda: setattr(QMessageBox, "question", _orig_q))

win = MainWindow()
atexit.register(lambda: (win.close(), win.deleteLater()))
win.resize(900, 600)
win.show()
QTest.qWaitForWindowExposed(win)
app.processEvents()


def node(t):
    return next((n for n in win.workspace.all_nodes() if n.title == t), None)


def titles():
    return sorted(n.title for n in win.workspace.all_nodes())


print("1) PŘEJMENOVÁNÍ a undo")
win._on_rename(node("Beta"), "Beta NOVA")
app.processEvents()
check("název se změnil", "Beta NOVA" in titles())
check("záznam undo je levný typ 'moved'",
      win.undo.entries and win.undo.entries[-1][0] == "moved")
win._undo()
app.processEvents()
check("undo vrátilo původní název",
      "Beta" in titles() and "Beta NOVA" not in titles())

print("2) PŘESUN (drag & drop) a undo")
win._on_reparent(node("Gama"), node("Alfa"))
app.processEvents()
g = node("Gama")
check("úkol je pod novým rodičem",
      g is not None and g.parent is not None and g.parent.title == "Alfa")
check("záznam undo je levný typ 'moved'",
      win.undo.entries and win.undo.entries[-1][0] == "moved")
win._undo()
app.processEvents()
g = node("Gama")
check("undo vrátilo úkol do kořene", g is not None and g.parent is None)

print("3) MAZÁNÍ a undo (i s podúkoly)")
win._current_node = node("Alfa")
win._delete_task()
app.processEvents()
check("úkol i podúkol jsou pryč",
      "Alfa" not in titles() and "Alfa sub" not in titles())
check("záznam undo je levný typ 'deleted'",
      win.undo.entries and win.undo.entries[-1][0] == "deleted")
win._undo()
app.processEvents()
check("undo obnovilo úkol", "Alfa" in titles())
check("undo obnovilo i podúkol", "Alfa sub" in titles())
restored = node("Alfa sub")
check("obnovený podúkol má správného rodiče",
      restored is not None and restored.parent is not None
      and restored.parent.title == "Alfa")

print("4) Undo nezálohuje celý workspace")
# u 'moved' se nekopíruje nic, u 'deleted' jen mazané podstromy
win._on_rename(node("Beta"), "Beta znovu")
app.processEvents()
kind, payload = win.undo.entries[-1]
check("'moved' nese jen cesty (žádná kopie dat)",
      kind == "moved" and isinstance(payload, tuple) and len(payload) == 3)

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
