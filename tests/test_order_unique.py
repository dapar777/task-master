"""Pořadí nového úkolu musí být jedinečné GLOBÁLNĚ, ne jen mezi viditelnými.

V Bez rušení s filtrem je vidět zlomek úkolů. Pořadí spočítané jen ze
sousedů ve výřezu (prev+1, nxt-1, střed) padalo na pořadí skrytého úkolu
a normalize_orders() pak při dalším přidání přečíslovala a uložila celý
strom (sekundy při stovkách úkolů)."""
import atexit
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_order_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

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
_s.setValue("view_mode", "cards")
_s.sync()

from app import mainwindow as mw  # noqa: E402
from app.storage import TaskNode, Workspace  # noqa: E402

# 60 kořenů × 3 podúkoly, skoro vše hotové; pár „probíhá" roztroušených
ws = Workspace(tmp)
ws.load()
visible_titles = []
for i in range(60):
    r = ws.create_root(f"Projekt {i:02d}")
    r.meta["_status"] = "done"
    r.save_meta()
    for j in range(3):
        c = ws.create_child_of(r, f"Ukol {i:02d}.{j}")
        if i % 12 == 5 and j == 1:
            c.meta["_status"] = "in_progress"
            visible_titles.append(c.title)
        else:
            c.meta["_status"] = "done"
        c.save_meta()
ws.load()

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


def all_orders():
    return [n.order for n in win.workspace.all_nodes()]


def orders_unique():
    o = all_orders()
    return len(set(o)) == len(o)


def count_saves(fn):
    """Kolikrát se během fn() zapsala metadata na disk."""
    orig = TaskNode.save_meta
    n = 0

    def counting(self):
        nonlocal n
        n += 1
        return orig(self)

    TaskNode.save_meta = counting
    try:
        fn()
    finally:
        TaskNode.save_meta = orig
    return n


win = mw.MainWindow()
win.filter_panel.apply_preset({"statuses": ["in_progress"], "sort_key": "order"})
win._populate()
app.processEvents()

by_title = {n.title: n for n in win.workspace.all_nodes()}
visible = [n for n in win._flat_sequence()]
print(f"1) Bez rušení: {len(visible)} viditelných z {len(list(win.workspace.all_nodes()))} úkolů")
check("filtr schoval většinu", 0 < len(visible) < 12)
check("pořadí je na začátku jedinečné", orders_unique())

# --- 2) přidávání úkolů dialogem přes skutečnou cestu (_new_task) ---
print("2) Nový úkol za aktuálním nekoliduje se skrytými sousedy")
cur = by_title[visible_titles[1]]
win._current_node = cur
win.detail.load(cur)
win._select_in_view(cur)
for k in range(6):
    vals = {"title": f"Novy {k}", "status": "in_progress", "priority": 5,
            "category": "", "tags": [], "flag": False}
    mw.TaskDialog.get = staticmethod(lambda *a, **kw: dict(vals))
    prev_cur = win._current_node
    win._new_task()
    app.processEvents()
    new = win._current_node
    check(f"  {k}: pořadí zůstalo jedinečné", orders_unique())
    seq = win._flat_sequence()
    check(f"  {k}: nový je hned za předchozím aktuálním",
          new in seq and prev_cur in seq and seq.index(new) == seq.index(prev_cur) + 1)
    check(f"  {k}: normalize_orders nic nepřepisuje",
          count_saves(win.workspace.normalize_orders) == 0)

# --- 3) _order_between přímo: sousedé ve výřezu vs. skryté pořadí ---
print("3) _order_between se vyhýbá obsazeným hodnotám mimo výřez")
a, b, hidden = by_title["Ukol 00.0"], by_title["Ukol 00.1"], by_title["Ukol 00.2"]
base = max(all_orders()) + 100.0
a.set_order(base + 10.0)
hidden.set_order(base + 11.0)
b.set_order(base + 12.0)
v = win._order_between([a, b], 1)
check("střed mezi 10 a 12 obejde skrytou 11", base + 10 < v < base + 12 and v != base + 11)
check("hodnota není obsazená", v not in set(all_orders()))
v = win._order_between([a], 1)  # za a: prev+1 by byla skrytá 11
check("za posledním se vyhne skryté prev+1", v > base + 10 and v not in set(all_orders()))
v = win._order_between([b], 0)  # před b: nxt-1 by byla skrytá 11
check("před prvním se vyhne skryté nxt-1", v < base + 12 and v not in set(all_orders()))
v = win._order_between([], 0)
check("prázdný výřez nedá 0.0 (obsazenou)", v not in set(all_orders()))

# --- 4) vyčerpaná mezera: skupina se přečísluje, ne celý strom ---
print("4) Vyčerpaná mezera nepřepisuje celý strom")
a.set_order(1.0)
b.set_order(math.nextafter(1.0, 2.0))
saves = {}


def exhausted():
    saves["v"] = win._order_between([a, b], 1)


n_saves = count_saves(exhausted)
v = saves["v"]
check("výsledek je jedinečný", v not in set(all_orders()))
check("pořadí skupiny zůstalo (a < nový < b)", a.order < v < b.order)
check(f"uložila se jen skupina ({n_saves} zápisy, ne {len(all_orders())})", n_saves <= 2)
check("strom je po opravě jedinečný", orders_unique())

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
