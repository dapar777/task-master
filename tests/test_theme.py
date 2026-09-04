"""Téma a nový vzhled: tokeny, chipy, karty se skupinami, přepínač tmavého tématu.

Hlídá hlavně to, co nevidí ostatní testy: že barvy žijí jen v theme.py,
že se obě témata dají aplikovat a že se s nimi karty i strom vykreslí."""
import atexit
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_theme_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

from app.constants import APP_NAME, ORG_NAME  # noqa: E402

_s = QSettings(ORG_NAME, APP_NAME)
_orig = {k: _s.value(k) for k in ("workspace", "view_mode", "theme")}


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
_s.setValue("theme", "light")
_s.sync()

from app import icons, theme  # noqa: E402
from app.cardview import CardView  # noqa: E402
from app.storage import Workspace  # noqa: E402
from app.tasktree import TaskTreeWidget  # noqa: E402
from app.widgets import TitleLabel  # noqa: E402

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")

# --- 1) barvy jen v theme.py (constants.py drží legacy tabulku pro staré testy) ---
print("1) Hex barvy žijí jen v theme.py")
offenders = []
for p in sorted((ROOT / "app").glob("*.py")):
    if p.name in ("theme.py", "constants.py"):
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if HEX.search(line):
            offenders.append(f"{p.name}:{i}")
check("žádný modul mimo theme.py nemá hex barvu " + (", ".join(offenders) if offenders else ""),
      not offenders)

# --- 2) tokeny a sémantické styly ---
print("2) Tokeny a styly")
for name in ("light", "dark"):
    t = theme.apply(app, name)
    check(f"{name}: téma se aplikovalo", theme.current().name == name and len(app.styleSheet()) > 1000)
    for st in ("todo", "in_progress", "waiting", "snoozed", "blocked", "done", "neznámý"):
        fg, bg, dot = theme.status_style(st)
        check(f"{name}: status_style({st}) dává tři hexy",
              all(HEX.fullmatch(x) for x in (fg, bg, dot)))
    for p in (0, 1, 5, 10, 11, "x", None):
        fg, bg, ramp = theme.priority_style(p)
        check(f"{name}: priority_style({p!r}) nespadne", all(HEX.fullmatch(x) for x in (fg, bg, ramp)))
    check(f"{name}: karta v Bez rušení není bílá", t.card.lower() not in ("#ffffff", "#fff"))
check("mix(): střed mezi černou a bílou", theme.mix("#000000", "#ffffff", 0.5) == "#808080")
check("ikona se vykreslí", not icons.pixmap("flag", 16, "#cb4b16").isNull())
theme.apply(app, "light")

# --- 3) TitleLabel má rezervu na akcenty patkového písma ---
print("3) TitleLabel")
plain = QLabel("Připravit podklady pro schůzku s Novákem")
plain.setFont(theme.title_font(14.5))
plain.setWordWrap(True)
title = TitleLabel("Připravit podklady pro schůzku s Novákem", 14.5)
check("výška pro šířku je větší než u holého QLabel",
      title.heightForWidth(300) > plain.heightForWidth(300))

# --- 4) karty se skupinami, chipy a odpočtem v obou tématech ---
print("4) Karty a strom v obou tématech")
ws = Workspace(tmp)
ws.load()
r = ws.create_root("Projekt")
a = ws.create_child_of(r, "Aktivní")
a.meta.update({"_status": "in_progress", "_priority": 9, "_flag": True, "_tags": ["x"]})
a.save_meta()
b = ws.create_child_of(r, "Čekající")
b.meta["_status"] = "waiting"
b.save_meta()
c = ws.create_child_of(r, "Odložený")
c.set_snooze(3600)
d = ws.create_child_of(r, "Hotový")
d.meta["_status"] = "done"
d.save_meta()
ws.load()
nodes = list(ws.all_nodes())
groups = {"in_progress": ("active", "Probíhá + Ke zpracování", False),
          "todo": ("active", "Probíhá + Ke zpracování", False),
          "waiting": ("waiting", "Čeká", False), "snoozed": ("waiting", "Čeká", False),
          "done": ("done", "Hotovo", False)}
order = {"active": 0, "waiting": 1, "done": 2}
seq = sorted(nodes, key=lambda n: order[groups[n.meta.get("_status", "todo")][0]])

for name in ("light", "dark"):
    theme.apply(app, name)
    cv = CardView()
    cv.resize(900, 700)
    cv.populate(seq, compact_fn=lambda n: n.meta.get("_status") == "done",
                group_fn=lambda n: groups[n.meta.get("_status", "todo")])
    app.processEvents()
    check(f"{name}: všechny karty vznikly", len(cv._cards) == len(seq))
    shown = [h.text() for h in cv._headers.values() if not h.isHidden()]
    check(f"{name}: nadpisy skupin jsou vidět ({shown})",
          set(shown) == {"PROBÍHÁ + KE ZPRACOVÁNÍ", "ČEKÁ", "HOTOVO"})
    card = cv._cards[str(c.path)]
    check(f"{name}: odložená karta má odpočet a Obnovit",
          card.countdown is not None and card.resume_btn is not None
          and card.countdown.property("phase") == "running")
    check(f"{name}: vlaječka je ikona, ne emoji",
          cv._cards[str(a.path)].flag_label is not None and "🚩" not in cv._cards[str(a.path)].title.text())
    check(f"{name}: úsporná karta je nižší než plná",
          cv._cards[str(d.path)].sizeHint().height() < cv._cards[str(a.path)].sizeHint().height())
    check(f"{name}: stránka karet se vykreslí", not cv.grab().isNull())

    tree = TaskTreeWidget()
    tree.resize(600, 400)
    tree.populate(ws.roots, True, lambda n: True)
    app.processEvents()
    check(f"{name}: strom s chipovým delegátem se vykreslí", not tree.grab().isNull())
    check(f"{name}: sloupec Úkol je pružný",
          tree.header().sectionResizeMode(0) == tree.header().ResizeMode.Stretch)

# --- 5) přepínač tmavého tématu v hlavním okně ---
print("5) Přepínač tématu")
theme.apply(app, "light")
from app.mainwindow import MainWindow  # noqa: E402
win = MainWindow()
win.show()
app.processEvents()
win.act["view.dark_theme"].setChecked(True)
app.processEvents()
check("akce přepne na tmavé téma", theme.is_dark())
check("volba se uložila do nastavení", QSettings(ORG_NAME, APP_NAME).value("theme") == "dark")
check("otisk karet obsahuje téma (přebudují se)",
      all(s[4] == "dark" for s in win.card_view._stamps.values()) or not win.card_view._stamps)
win.act["view.dark_theme"].setChecked(False)
app.processEvents()
check("a zpět na světlé", not theme.is_dark())
check("hlavička má přepínač zobrazení na kartách", win.view_segment.current() == "cards")
win._set_view_mode("tree")
app.processEvents()
check("panel filtrů se přestěhoval do levého panelu",
      win.filter_panel.parent() is win.left_layout.parentWidget())
win._set_view_mode("cards")
app.processEvents()
check("a zpět nad karty", win.filter_panel.parent() is win.filter_host)
win.close()

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
