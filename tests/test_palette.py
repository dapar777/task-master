"""Příkazová paleta: víceúrovňové položky, hluboké hledání, naposledy použité,
hledání úkolů, prefixy, keep_open a to, že žádná akce z menu v paletě nechybí."""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_palette_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

from app.constants import APP_NAME, ORG_NAME  # noqa: E402

_s = QSettings(ORG_NAME, APP_NAME)
_orig = {k: _s.value(k) for k in ("workspace", "view_mode", "theme", "zoom", "palette_recent")}


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
_s.setValue("theme", "light")
_s.remove("zoom")
_s.remove("palette_recent")
_s.sync()

from app import theme  # noqa: E402
from app.commandpalette import ENTRY_ROLE, CommandPalette, parse_mode  # noqa: E402
from app.storage import Workspace  # noqa: E402

theme.apply(app, "light", zoom=1.0)

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


ws = Workspace(tmp)
ws.load()
r = ws.create_root("Projekt Alfa")
a = ws.create_child_of(r, "Připravit podklady")
a.meta.update({"_status": "in_progress", "_priority": 7, "_category": "Práce", "_tags": ["urgent"]})
a.save_meta()
b = ws.create_child_of(r, "Zavolat Novákovi")
b.meta.update({"_category": "Telefonáty"})
b.save_meta()
c = ws.create_child_of(a, "Podklad – tabulka")
ws.create_root("Beta projekt")
ws.load()

from app.mainwindow import MainWindow  # noqa: E402

win = MainWindow()
win.resize(1200, 760)
win.show()
QTest.qWaitForWindowExposed(win)
app.processEvents()
win.tree.select_path(str(a.path))
app.processEvents()
check("aktivní úkol je „Připravit podklady“", win._current_node is not None and win._current_node.title == "Připravit podklady")


def live(n):
    """Uzel v instanci workspace hlavního okna (test má vlastní Workspace)."""
    return win.workspace.node_by_id(n.task_id)


def labels(pal):
    return [pal.list.item(i).text() for i in range(pal.list.count())]


def entries(pal):
    return [pal.list.item(i).data(ENTRY_ROLE) for i in range(pal.list.count())]


def make():
    return CommandPalette(win._build_palette_commands(), win, recent=win._palette_recent(),
                          on_run=lambda p: win.settings.setValue("palette_recent", [p] + win._palette_recent()),
                          extra_search=lambda q: win._palette_task_entries(q, limit=12),
                          mode_search=lambda m, q: win._palette_task_entries(q, limit=200))


def type_(pal, text):
    """Napíše dotaz a hned vyhodnotí (hledání úkolů je jinak debouncované)."""
    pal.search.setText(text)
    pal._search_timer.stop()
    pal._filter(pal.search.text())
    app.processEvents()


def pick(pal, text):
    """Vybere první položku, jejíž text obsahuje `text`, a spustí ji."""
    for i in range(pal.list.count()):
        if text in pal.list.item(i).text():
            pal.list.setCurrentRow(i)
            pal._run_current()
            return True
    return False


# --- 1) prefixy a parse_mode ---
print("1) parse_mode")
check("bez prefixu", parse_mode("stav") == ("all", "stav"))
check("mezera = jen příkazy", parse_mode(" stav") == ("commands", "stav"))
check("u = jen úkoly", parse_mode("u novák") == ("tasks", "novák"))
check("„u“ bez mezery je běžný dotaz", parse_mode("undo") == ("all", "undo"))

# --- 2) úplnost: každá akce z menu je v paletě ---
print("2) Úplnost registru")
cmds = win._build_palette_commands()
top = {e["label"] for e in cmds}
missing = []
for cid, act in win.act.items():
    if cid == "app.command_palette" or cid.startswith("task.status_"):
        continue
    lbl = win.shortcuts.label(cid) if cid in win.shortcuts.all_command_ids() else act.text()
    if lbl not in top:
        missing.append(cid)
check("žádná akce z menu nechybí " + (", ".join(missing) if missing else ""), not missing)
check("popisky na kořeni jsou jedinečné (klíč naposledy použitých)", len(top) == len(cmds))
branches = [e for e in cmds if e.get("children") is not None or callable(e.get("search"))]
check("paleta má aspoň 15 víceúrovňových položek", len(branches) >= 15)
for e in cmds:
    if e.get("children") is not None:
        kids = e["children"]() if callable(e["children"]) else e["children"]
        assert isinstance(kids, list) and kids, e["label"]
check("všechny podúrovně jdou postavit", True)

# --- 3) kořen: hledání, hluboké hledání, sestup a návrat ---
print("3) Úrovně a hledání")
pal = make()
pal.show()
app.processEvents()
n_all = pal.list.count()
check("kořen ukazuje všechny příkazy", n_all == len(cmds))
type_(pal, "sestupně")
deep = [e for e in entries(pal) if e.get("_deep")]
check("hluboké hledání najde „Řadit podle › Název › Sestupně“",
      any("Řadit podle  ›  Název  ›  Sestupně" in l for l in labels(pal)) and deep)
type_(pal, " stav")
check("prefix mezera = jen příkazy (bez úkolů)", not any(e.get("_dynamic") for e in entries(pal)) and pal.list.count() > 0)
check("drobečky ukazují režim", "jen příkazy" in pal.crumb.text())
type_(pal, "")
check("sestup do „Stav“", pick(pal, "Úkol  ·  Stav  ›") and pal._stack and pal.crumb.text().endswith("Stav"))
kids = entries(pal)
check("podúroveň Stav má všechny stavy a aktuální je zaškrtnutý",
      len(kids) == 6 and next(e for e in kids if e["label"] == "Probíhá").get("checked") is True)
QTest.keyClick(pal.search, Qt.Key.Key_Backspace)
app.processEvents()
check("Backspace v prázdném poli vrátí na kořen", not pal._stack and pal.list.count() == n_all)
pal.close()

# --- 4) spuštění listu podúrovně mění stav a zapíše „naposledy použité“ ---
print("4) Spuštění a naposledy použité")
pal = make()
pal.show()
pick(pal, "Úkol  ·  Stav  ›")
app.processEvents()
pick(pal, "Čeká      ") or pick(pal, "Stav  ·  Čeká")
app.processEvents()
QTest.qWait(50)
app.processEvents()
check("stav aktivního úkolu je Čeká", live(a).meta.get("_status") == "waiting")
rec = win._palette_recent()
check("cesta příkazu se uložila do nastavení", rec and rec[0] == "Stav|Čeká")
pal = make()
pal.show()
app.processEvents()
first = entries(pal)[0]
check("naposledy použité je nahoře, zploštělé", first.get("_recent") and first["label"] == "Stav  ›  Čeká")
pal.close()

# --- 5) víceúrovňové řazení, zobrazení, zoom, téma ---
print("5) Řazení / zobrazení / zoom / téma")
pal = make()
pal.show()
type_(pal, "priorita sestupně")
check("řazení podle priority sestupně se spustí", pick(pal, "Řadit podle  ›  Priorita  ›  Sestupně"))
app.processEvents()
check("panel filtrů má řazení priorita sestupně", win.filter_panel.current_sort() == ("priority", True))
pal = make()
pal.show()
type_(pal, "bez rušení")
check("přepnutí do Bez rušení", pick(pal, "Zobrazení  ›  Bez rušení"))
app.processEvents()
check("režim karet aktivní", win._view_mode == "cards")
pal = make()
pal.show()
type_(pal, "zoom 125")
check("zoom 125 % z palety", pick(pal, "Zoom  ›  125 %"))
app.processEvents()
check("zoom je 125 %", abs(theme.zoom() - 1.25) < 1e-6)
win._apply_zoom(1.0)
pal = make()
pal.show()
type_(pal, "téma tmavé")
check("tmavé téma z palety", pick(pal, "Téma  ›  Tmavé"))
app.processEvents()
check("je tmavé", theme.is_dark())
win.act["view.dark_theme"].setChecked(False)
app.processEvents()

# --- 6) filtr: keep_open přepíná kritéria, paleta zůstává otevřená ---
print("6) Filtr")
pal = make()
pal.show()
pick(pal, "Filtr: stav  ›")
app.processEvents()
row_before = pal.list.count()
check("položky stavů nejsou zaškrtnuté", not any(e.get("checked") for e in entries(pal)))
pal.list.setCurrentRow(1)  # Probíhá
pal._run_current()
app.processEvents()
check("paleta zůstala otevřená na stejné úrovni", pal.isVisible() and pal._stack and pal.list.count() == row_before)
check("filtr má stav Probíhá", win.filter_panel.current_filters()["statuses"] == ["in_progress"])
check("položka se ukazuje zaškrtnutá", entries(pal)[1].get("checked") is True)
pal.close()
pal = make()
pal.show()
pick(pal, "Filtr: kategorie  ›")
app.processEvents()
check("kategorie z workspace", {e["label"] for e in entries(pal)} == {"Práce", "Telefonáty"})
pal.close()
pal = make()
pal.show()
check("zrušit filtr", pick(pal, "Filtr  ·  Zrušit filtr"))
app.processEvents()
check("filtr je prázdný", win.filter_panel.current_filters()["statuses"] == [])

# --- 7) úkoly: extra_search na kořeni, prefix u, vyhledávací úroveň, priorita, odklad ---
print("7) Úkoly")
pal = make()
pal.show()
type_(pal, "novák")
hits = [e for e in entries(pal) if e.get("_dynamic")]
check("kořen nabídne úkol podle názvu (3+ znaky)", any(e["label"] == "Zavolat Novákovi" for e in hits))
type_(pal, "u podklad")
check("prefix u: jen úkoly, i podúkol", all(e.get("_dynamic") for e in entries(pal))
      and {e["label"] for e in entries(pal)} == {"Připravit podklady", "Podklad – tabulka"})
check("přesná shoda začátku názvu je první", entries(pal)[0]["label"] == "Podklad – tabulka")
type_(pal, "")
pick(pal, "Přejít na úkol")
app.processEvents()
check("vyhledávací úroveň má počet úkolů v drobečcích", "5 úkolů" in pal.crumb.text())
type_(pal, "tabulka")
check("přejít na podúkol", pick(pal, "Podklad – tabulka"))
app.processEvents()
check("podúkol je aktivní a pohled je strom", win._current_node is not None and win._current_node.task_id == c.task_id and win._view_mode == "tree")

win.tree.select_path(str(a.path))
app.processEvents()
pal = make()
pal.show()
type_(pal, "priorita p3")
check("priorita P3 z palety", pick(pal, "Priorita  ›  P3"))
app.processEvents()
check("úkol má prioritu 3", live(a).meta.get("_priority") == 3)
pal = make()
pal.show()
type_(pal, "odložit 30")
check("odklad 30 minut", pick(pal, "Odložit o  ›  30 minut"))
QTest.qWait(50)
app.processEvents()
check("úkol je odložený s ~30 min", live(a).meta.get("_status") == "snoozed" and 1700 < (live(a).snooze_remaining() or 0) <= 1800)
check("interval se zapamatoval jako poslední", win._last_snooze == (0, 0, 30))

# --- 8) podúkoly / nadřazený / _open_command_palette ---
print("8) Navigace a otevření palety")
pal = make()
pal.show()
pick(pal, "Podúkoly aktuálního úkolu")
app.processEvents()
check("podúroveň s podúkoly", [e["label"] for e in entries(pal)] == ["Podklad – tabulka"])
pal.close()
QDialog.exec = lambda self: (self.show(), app.processEvents(), 0)[2]
try:
    win._open_command_palette()
    check("_open_command_palette otevře paletu s naposledy použitými", True)
except Exception as ex:  # noqa: BLE001
    check(f"_open_command_palette bez pádu ({type(ex).__name__}: {ex})", False)

win.close()
print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
