"""Headless kontrola: sbalený stav a pozice rolování přežijí populate()."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.storage import Workspace  # noqa: E402
from app.tasktree import TaskTreeWidget  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_test_"))
ws = Workspace(tmp)
ws.load()

parent = ws.create_root("Rodic")
child_a = parent.create_child("Podukol A")
parent.create_child("Podukol B")
other = ws.create_root("Druhy koren")
other.create_child("Jeho podukol")
ws.load()

tree = TaskTreeWidget()
tree.resize(400, 300)
match_all = lambda n: True


def paths_expanded():
    """{cesta: rozbaleno} pro položky, které mají děti."""
    out = {}
    stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    while stack:
        it = stack.pop()
        if it is None:
            continue
        n = it.data(0, 0x0100)  # Qt.UserRole
        if n is not None and it.childCount():
            out[n.title] = it.isExpanded()
        for i in range(it.childCount()):
            stack.append(it.child(i))
    return out


def find(title):
    stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    while stack:
        it = stack.pop()
        if it is None:
            continue
        n = it.data(0, 0x0100)
        if n is not None and n.title == title:
            return it
        for i in range(it.childCount()):
            stack.append(it.child(i))
    return None


fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


print("1) první naplnění -> vše rozbalené")
tree.populate(ws.roots, True, match_all)
check("Rodic rozbalen", paths_expanded().get("Rodic") is True)
check("Druhy koren rozbalen", paths_expanded().get("Druhy koren") is True)

print("2) uživatel sbalí 'Rodic', pak přebudování (např. změna stavu)")
find("Rodic").setExpanded(False)
tree.populate(ws.roots, True, match_all)
check("Rodic zůstal sbalený", paths_expanded().get("Rodic") is False)
check("Druhy koren zůstal rozbalený", paths_expanded().get("Druhy koren") is True)

print("3) přidání nového tasku strom nerozbalí")
ws.create_root("Novy task")
ws.load()
tree.populate(ws.roots, True, match_all)
check("Rodic pořád sbalený po přidání tasku", paths_expanded().get("Rodic") is False)

print("4) přepnutí do plochého režimu a zpět zachová sbalení")
tree.populate(ws.roots, False, match_all)
tree.populate(ws.roots, True, match_all)
check("Rodic sbalený i po návratu ze seznamu", paths_expanded().get("Rodic") is False)

print("5) výběr uzlu pod sbaleným rodičem ho zviditelní")
tree.select_path(str(child_a.path))
check("Rodic rozbalen kvůli výběru potomka", paths_expanded().get("Rodic") is True)
check("vybrán Podukol A", tree.current_node() is not None
      and tree.current_node().title == "Podukol A")

print("6) select_paths (vícevýběr) taky rozbalí předky")
find("Rodic").setExpanded(False)
tree.populate(ws.roots, True, match_all)
check("Rodic zase sbalený", paths_expanded().get("Rodic") is False)
tree.select_paths([child_a.path, other.path], emit=False)
check("Rodic rozbalen kvůli vícevýběru", paths_expanded().get("Rodic") is True)
check("označeny 2 uzly", len(tree.selected_nodes()) == 2)

print("7) PŘEJMENOVÁNÍ sbaleného úkolu nerozbalí jeho větev")
tree.populate(ws.roots, True, match_all)
find("Rodic").setExpanded(False)
tree.populate(ws.roots, True, match_all)
check("Rodic sbalený před přejmenováním", paths_expanded().get("Rodic") is False)
parent.rename_dir("Rodic prejmenovany")
ws.load()
parent = next(n for n in ws.roots if n.title == "Rodic prejmenovany")
child_a = next(c for c in parent.children if c.title == "Podukol A")
tree.populate(ws.roots, True, match_all)
check("po přejmenování zůstal sbalený (stabilní _id)",
      paths_expanded().get("Rodic prejmenovany") is False)

print("8) PŘESUN sbaleného úkolu pod jiný nerozbalí jeho větev")
other = next(n for n in ws.roots if n.title == "Druhy koren")
parent.move_to(other.path)
ws.load()
parent = next(c for c in next(n for n in ws.roots if n.title == "Druhy koren").children
              if c.title == "Rodic prejmenovany")
tree.populate(ws.roots, True, match_all)
check("po přesunu zůstal sbalený",
      paths_expanded().get("Rodic prejmenovany") is False)

print("9) pozice rolování přežije přebudování")
for i in range(40):
    ws.create_root(f"Fill {i:02d}")
ws.load()
tree.populate(ws.roots, True, match_all)
tree.show()
sb = tree.verticalScrollBar()
if sb.maximum() > 0:
    target = sb.maximum() // 2
    sb.setValue(target)
    before = sb.value()
    tree.populate(ws.roots, True, match_all)
    check(f"scroll zachován ({before} -> {sb.value()})", sb.value() == before)
else:
    print("  SKIP  scrollbar nemá rozsah v offscreen režimu")

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
