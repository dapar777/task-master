"""End-to-end: zaškrtnutí stavu ve stromu nesmí přehodit výběr na první task."""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt, QSettings  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_focus_"))
# po sobě ukliď i při pádu testu
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

# MainWindow si dělá QSettings(ORG_NAME, APP_NAME) NATVRDO, takže samotné
# setOrganizationName/setApplicationName ho neizoluje – bez přesměrování by
# si při startu načetl reálný workspace uživatele a přepsal v něm metadata.
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
ws = Workspace(tmp)
ws.load()
for i in range(5):
    ws.create_root(f"Task {i}")
ws.load()

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


win = MainWindow()
win.workspace = ws
win.tree.resolver = ws.node_by_id
win._view_mode = "tree"
win._populate()

titles = [n.title for n in ws.roots]
print(f"pořadí ve stromu: {titles}")


def item_by_title(t):
    for i in range(win.tree.topLevelItemCount()):
        it = win.tree.topLevelItem(i)
        if it.data(0, Qt.ItemDataRole.UserRole).title == t:
            return it
    return None


def current_title():
    n = win.tree.current_node()
    return n.title if n else None


first_title = win.tree.topLevelItem(0).data(0, Qt.ItemDataRole.UserRole).title
target_title = "Task 3"

print("1) STROM: zaškrtnutí 'Task 3' nechá výběr na 'Task 3'")
win.tree.select_path(str(next(n for n in ws.roots if n.title == target_title).path))
check("výběr před změnou = Task 3", current_title() == target_title)
it = item_by_title(target_title)
it.setCheckState(0, Qt.CheckState.Checked)   # spustí statusToggled -> _apply_status_to
app.processEvents()                           # doběhne QTimer.singleShot(0, ...)
node3 = next(n for n in ws.roots if n.title == target_title)
check("stav se změnil na done", node3.meta.get("_status") == "done")
check(f"výběr ZŮSTAL na Task 3 (je {current_title()!r}, ne {first_title!r})",
      current_title() == target_title)

print("2) STROM: odškrtnutí zpět taky nepřeskočí")
it = item_by_title(target_title)
it.setCheckState(0, Qt.CheckState.Unchecked)
app.processEvents()
check("stav zpět na todo", node3.meta.get("_status") == "todo")
check(f"výběr stále Task 3 (je {current_title()!r})", current_title() == target_title)

print("3) KARTY: stav JINÉ karty pohled nepřehazuje")
win._view_mode = "cards"
win._populate()
app.processEvents()

# 3a) stav JINÉ než aktivní karty – aktivní se nemění, pohled nepřeskakuje
active = next(n for n in ws.roots if n.title == "Task 4")
win._current_node = active
win._select_in_view(active)
app.processEvents()
node2 = next(n for n in ws.roots if n.title == "Task 2")
win._apply_status_to([node2], "done")
app.processEvents()
QTest.qWait(60)
app.processEvents()
check("stav JINÉ karty nechá aktivní kartu být",
      win._current_node is not None and win._current_node.title == "Task 4")

# 3b) stav AKTIVNÍ karty, která tím spadne do nižší skupiny -> skok nahoru
print("4) KARTY: dokončení AKTIVNÍ karty skočí na první")
win._apply_status_to([win._current_node], "done")
app.processEvents()
QTest.qWait(60)
app.processEvents()
if win.card_view._order:
    top_path = win.card_view._order[0]
    check("po dokončení aktivní karty je aktivní první karta shora",
          win._current_node is not None and str(win._current_node.path) == top_path)
else:
    print("  SKIP  prázdné karty")

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
