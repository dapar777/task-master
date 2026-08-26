"""Klávesa kontextového menu (Menu / Shift+F10) ve všech zobrazeních.

Strom i seznam ji dostávají přes CustomContextMenu automaticky. V Bez rušení
ji ale karta nedostane – fokus drží scroll area, ne karta – takže ji musí
odchytit CardView a nasměrovat na aktivní kartu.
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, QSettings  # noqa: E402
from PySide6.QtGui import QContextMenuEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_ctxkey_"))
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
for t in ("Alfa", "Beta"):
    ws.create_root(t)
ws.load()

for _n in ("question", "warning", "information"):
    setattr(QMessageBox, _n,
            staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

# menu jen počítej, ať test nečeká na zavření
opened = {"tree": 0, "card": 0, "node": None}
_orig_tree = MainWindow._show_tree_menu
_orig_card = MainWindow._show_card_menu
atexit.register(lambda: (setattr(MainWindow, "_show_tree_menu", _orig_tree),
                         setattr(MainWindow, "_show_card_menu", _orig_card)))
MainWindow._show_tree_menu = lambda self, pos: opened.__setitem__(
    "tree", opened["tree"] + 1)
MainWindow._show_card_menu = lambda self, node, pos: (
    opened.__setitem__("card", opened["card"] + 1),
    opened.__setitem__("node", node))

win = MainWindow()
atexit.register(lambda: (win.close(), win.deleteLater()))
win.resize(900, 600)
win.show()
QTest.qWaitForWindowExposed(win)
app.processEvents()


def node(t):
    return next(n for n in win.workspace.all_nodes() if n.title == t)


def press_menu_key(widget):
    """Pošle událost, jakou vyvolá klávesa Menu / Shift+F10."""
    ev = QContextMenuEvent(QContextMenuEvent.Reason.Keyboard, QPoint(5, 5),
                           widget.mapToGlobal(QPoint(5, 5)))
    app.sendEvent(widget, ev)
    app.processEvents()


print("1) Klávesa otevře menu ve všech třech zobrazeních")
for mode in ("tree", "list", "cards"):
    win._view_mode = mode
    win._populate()
    app.processEvents()
    if mode == "cards":
        win._current_node = node("Alfa")
        win._select_in_view(node("Alfa"))
        widget = win.card_view
    else:
        win.tree.setCurrentItem(win.tree.topLevelItem(0))
        widget = win.tree
    app.processEvents()
    before = dict(opened)
    widget.setFocus()
    press_menu_key(widget)
    fired = (opened["tree"] > before["tree"]) or (opened["card"] > before["card"])
    check(f"{mode}: klávesa otevřela kontextové menu", fired)

print("2) V kartách míří na aktivní kartu")
win._view_mode = "cards"
win._populate()
app.processEvents()
win._current_node = node("Beta")
win._select_in_view(node("Beta"))
app.processEvents()
opened["node"] = None
win.card_view.setFocus()
press_menu_key(win.card_view)
check("menu dostalo aktivní kartu",
      opened["node"] is not None and opened["node"].title == "Beta")

print("3) Bez vybrané karty to nespadne")
win.card_view._focus = None
try:
    press_menu_key(win.card_view)
    check("prázdný výběr nespadne", True)
except Exception as e:  # noqa: BLE001
    check(f"prázdný výběr nespadne ({type(e).__name__})", False)

print("4) Pravé tlačítko funguje dál")
win._current_node = node("Alfa")
win._select_in_view(node("Alfa"))
app.processEvents()
before = opened["card"]
card = win.card_view._cards.get(str(node("Alfa").path))
if card is not None:
    ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5),
                           card.mapToGlobal(QPoint(5, 5)))
    app.sendEvent(card, ev)
    app.processEvents()
check("myš menu otevře taky", opened["card"] > before)

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
