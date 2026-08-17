"""Dialogy a uložené filtry – otevřou se bez pádu, filtry přežijí uložení.

Příkazová paleta, správa filtrů, zkratky a statistiky se volají přes stejné
metody jako z menu. Uložené filtry se ukládají do JSON – poškozený soubor
nesmí položit start aplikace.
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
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_dlg_"))
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
from app.savedfilters import FilterStore, SavedFilter  # noqa: E402
from app.storage import Workspace  # noqa: E402

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


print("1) Uložené filtry: uložení, načtení, vyhledání, odebrání")
fp = tmp / "filters.json"
store = FilterStore(fp)
sf = SavedFilter(name="Jen hotové", statuses=["done"], view="cards",
                 shortcut="Ctrl+1")
store.add(sf)
store.save()
reloaded = FilterStore(fp)
reloaded.load()
check("filtr se načetl zpět", len(reloaded.filters) == 1)
got = reloaded.filters[0]
check("název zachován", got.name == "Jen hotové")
check("podmínky zachovány", got.statuses == ["done"])
check("zobrazení zachováno", got.view == "cards")
check("zkratka zachována", got.shortcut == "Ctrl+1")
check("get() podle id najde filtr", reloaded.get(got.id) is not None)
reloaded.remove(got.id)
reloaded.save()
after = FilterStore(fp)
after.load()
check("po odebrání je prázdno", len(after.filters) == 0)

print("2) Poškozený JSON s filtry nepoloží načtení")
fp.write_text("{{{ neplatny json", encoding="utf-8")
try:
    broken = FilterStore(fp)
    broken.load()
    check("load() prošel", True)
    check("filtry jsou prázdné", len(broken.filters) == 0)
except Exception as e:  # noqa: BLE001
    check(f"poškozený JSON bez pádu ({type(e).__name__})", False)

print("3) Dialogy se otevřou přes stejné cesty jako z menu")
ws = Workspace(tmp)
ws.load()
for i in range(4):
    ws.create_root(f"Ukol {i}")
ws.load()

# Zastínění vrať zpět, i když test spadne – jinak by v jednom procesu
# ovlivnilo další sady (dialogy by se tiše přeskakovaly).
_orig_box = {n: getattr(QMessageBox, n)
             for n in ("question", "warning", "information")}
_orig_exec = QDialog.exec


def _restore_dialogs():
    for n, fn in _orig_box.items():
        setattr(QMessageBox, n, fn)
    QDialog.exec = _orig_exec


atexit.register(_restore_dialogs)

for _name in ("question", "warning", "information"):
    setattr(QMessageBox, _name,
            staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
# modální exec() by test zablokoval – jen zobraz a vrať se
QDialog.exec = lambda self: (self.show(), app.processEvents(), 0)[2]

win = MainWindow()
win.resize(1000, 650)
win.show()
QTest.qWaitForWindowExposed(win)
app.processEvents()

for label, method in (
    ("příkazová paleta", "_open_command_palette"),
    ("statistiky (F8)", "_open_stats"),
    ("správa filtrů", "_manage_filters"),
):
    try:
        getattr(win, method)()
        app.processEvents()
        check(f"{label} se otevřela bez pádu", True)
    except Exception as e:  # noqa: BLE001
        check(f"{label} bez pádu ({type(e).__name__}: {e})", False)

print("4) Dialog zkratek se vykreslí")
try:
    from app.shortcutdialog import ShortcutDialog  # noqa: E402
    d = ShortcutDialog(win.shortcuts, win)
    d.resize(600, 400)
    d.show()
    app.processEvents()
    check("dialog zkratek vykreslen", d.grab().width() > 50)
    d.close()
except Exception as e:  # noqa: BLE001
    check(f"dialog zkratek bez pádu ({type(e).__name__}: {e})", False)

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
win.close()
win.deleteLater()
app.processEvents()   # doruč deleteLater hned, ať okno nevisí do konce procesu
sys.exit(1 if fails else 0)
