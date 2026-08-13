"""End-to-end přes MainWindow: přesun (drag&drop) a přejmenování (F2)
nesmí rozbalit sbalené větve, kterých se netýkají."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
QApplication.setOrganizationName("TaskMasterTest")
QApplication.setApplicationName("TaskMasterTest_" + str(os.getpid()))

from app.mainwindow import MainWindow  # noqa: E402
from app.storage import Workspace  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="tm_reparent_"))
ws = Workspace(tmp)
ws.load()

# A (se 2 podúkoly), B (se 2 podúkoly), C samostatný
a = ws.create_root("Alfa")
a.create_child("Alfa sub 1")
a.create_child("Alfa sub 2")
b = ws.create_root("Beta")
b.create_child("Beta sub 1")
b.create_child("Beta sub 2")
ws.create_root("Cecko")
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


def expanded_map():
    out = {}
    stack = [win.tree.topLevelItem(i) for i in range(win.tree.topLevelItemCount())]
    while stack:
        it = stack.pop()
        if it is None:
            continue
        n = it.data(0, Qt.ItemDataRole.UserRole)
        if n is not None and it.childCount():
            out[n.title] = it.isExpanded()
        for i in range(it.childCount()):
            stack.append(it.child(i))
    return out


def item(title):
    stack = [win.tree.topLevelItem(i) for i in range(win.tree.topLevelItemCount())]
    while stack:
        it = stack.pop()
        if it is None:
            continue
        n = it.data(0, Qt.ItemDataRole.UserRole)
        if n is not None and n.title == title:
            return it
        for i in range(it.childCount()):
            stack.append(it.child(i))
    return None


def node(title):
    return next((n for n in ws.all_nodes() if n.title == title), None)


print("1) sbal 'Alfa' i 'Beta'")
item("Alfa").setExpanded(False)
item("Beta").setExpanded(False)
win._populate()
check("Alfa sbalená", expanded_map().get("Alfa") is False)
check("Beta sbalená", expanded_map().get("Beta") is False)

print("2) PŘEJMENOVÁNÍ 'Cecko' (přes _on_rename) nerozbalí Alfa/Beta")
win._on_rename(node("Cecko"), "Cecko nove")
app.processEvents()
check("Alfa pořád sbalená", expanded_map().get("Alfa") is False)
check("Beta pořád sbalená", expanded_map().get("Beta") is False)
check("přejmenování proběhlo", node("Cecko nove") is not None)

print("3) PŘEJMENOVÁNÍ sbalené 'Alfa' ji nechá sbalenou")
win._on_rename(node("Alfa"), "Alfa nova")
app.processEvents()
check("Alfa nova zůstala sbalená", expanded_map().get("Alfa nova") is False)
check("Beta pořád sbalená", expanded_map().get("Beta") is False)

print("4) PŘESUN (drag&drop) 'Cecko nove' pod 'Beta' – Alfa zůstane sbalená")
win._on_reparent(node("Cecko nove"), node("Beta"))
app.processEvents()
check("Alfa nova stále sbalená", expanded_map().get("Alfa nova") is False)
check("přesun proběhl (Cecko pod Beta)",
      node("Cecko nove") is not None
      and node("Cecko nove").parent is not None
      and node("Cecko nove").parent.title == "Beta")
# cíl (Beta) se rozbalí schválně – ať je vidět, kam úkol spadl
check("Beta rozbalená, aby byl přesunutý úkol vidět",
      expanded_map().get("Beta") is True)

print("5) PŘESUN sbalené 'Alfa nova' pod 'Beta' – po přesunu zůstane sbalená")
win._on_reparent(node("Alfa nova"), node("Beta"))
app.processEvents()
check("Alfa nova sbalená i po přesunu",
      expanded_map().get("Alfa nova") is False)
check("Alfa nova je pod Beta",
      node("Alfa nova").parent is not None
      and node("Alfa nova").parent.title == "Beta")

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
