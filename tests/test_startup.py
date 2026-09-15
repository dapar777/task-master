"""Start bez konzole: nedostupný uložený prostor nesmí okno potichu shodit.

Uložený prostor na odpojeném disku (Google Drive) -> varování, volba jiného
prostoru, jinak výchozí místní prostor bez přepsání uložené cesty. Neošetřená
výjimka -> `crash.log` + dialog (`main.excepthook`), ne tiché zmizení pythonw.
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
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_startup_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

from app.constants import APP_NAME, ORG_NAME  # noqa: E402

# MainWindow čte QSettings(ORG_NAME, APP_NAME) natvrdo – přesměruj a po testu vrať
KEYS = ("workspace", "view_mode", "mail_interval_min")
_s = QSettings(ORG_NAME, APP_NAME)
_orig = {k: _s.value(k) for k in KEYS}


def _restore_settings():
    s = QSettings(ORG_NAME, APP_NAME)
    for k, v in _orig.items():
        if v is None:
            s.remove(k)
        else:
            s.setValue(k, v)
    s.sync()


atexit.register(_restore_settings)

# „nedostupný“ prostor: cesta pod obyčejným souborem – mkdir/stat vyhodí OSError
# stejně jako odpojený disk (PermissionError), jen deterministicky
blocker = tmp / "odpojeny-disk"
blocker.write_text("soubor, ne adresář", encoding="utf-8")
broken = blocker / "tasks"
_s.setValue("workspace", str(broken))
_s.setValue("view_mode", "tree")
_s.setValue("mail_interval_min", 0)
_s.sync()

from app import mailimport, theme  # noqa: E402

mailimport._cred_read = lambda: None

import app.mainwindow as mw  # noqa: E402
from app.mainwindow import MainWindow  # noqa: E402

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


theme.apply(app, "light", zoom=1.0)
# výchozí prostor je normálně <repo>/workspace – test na něj sahat nesmí
default_ws = tmp / "vychozi"
MainWindow._default_workspace = lambda self: default_ws

shown = []
mw.QMessageBox.warning = staticmethod(lambda parent, title, text, *a, **k: shown.append((title, text)))

print("1) Uložený prostor nejde otevřít, uživatel nic nevybere -> výchozí místní, cesta zůstane")
mw.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
win = MainWindow()
win._import_mail_auto = lambda: None
check("okno vzniklo (žádná výjimka)", win is not None and win.workspace is not None)
check("varování zmínilo cestu", shown and str(broken) in shown[-1][1])
check("otevřel se výchozí místní prostor", Path(win.workspace.root) == default_ws and default_ws.is_dir())
check("uložená cesta zůstala pro příští start", _s.value("workspace") == str(broken))
check("stavový řádek to hlásí", "nejde otevřít" in win.status.currentMessage())
check("hlavička ukazuje skutečně otevřený prostor", str(default_ws) in win.header_ws.text())
win.close()
win.deleteLater()
app.processEvents()

print("2) Uživatel vybere jiný prostor -> otevře se a uloží")
chosen = tmp / "novy-prostor"
chosen.mkdir()
shown.clear()
mw.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(chosen))
win = MainWindow()
win._import_mail_auto = lambda: None
check("varování se ukázalo", bool(shown))
check("otevřel se vybraný prostor", Path(win.workspace.root) == chosen)
check("vybraný prostor je uložený", _s.value("workspace") == str(chosen))
win.close()
win.deleteLater()
app.processEvents()

print("3) Dostupný prostor se otevře bez dialogů")
shown.clear()
win = MainWindow()
win._import_mail_auto = lambda: None
check("bez varování", not shown and Path(win.workspace.root) == chosen)
win.close()
win.deleteLater()
app.processEvents()

print("4) excepthook: crash.log + dialog")
import main as launcher  # noqa: E402

log = tmp / "cfg" / "crash.log"
launcher.crash_log_path = lambda: (log.parent.mkdir(parents=True, exist_ok=True), log)[1]
critical = []
launcher.QMessageBox.critical = staticmethod(lambda parent, title, text, *a, **k: critical.append((title, text)))
_orig_hook = sys.__excepthook__
sys.__excepthook__ = lambda *a: None  # konzole testu nemusí vidět úmyslný traceback
try:
    try:
        raise RuntimeError("úmyslná chyba při startu")
    except RuntimeError:
        launcher.excepthook(*sys.exc_info())
finally:
    sys.__excepthook__ = _orig_hook
check("crash.log obsahuje traceback", log.exists() and "úmyslná chyba při startu" in log.read_text(encoding="utf-8")
      and "RuntimeError" in log.read_text(encoding="utf-8"))
check("dialog ukázal chybu i cestu k logu", critical and "úmyslná chyba" in critical[-1][1]
      and str(log) in critical[-1][1])
check("main() instaluje excepthook", "sys.excepthook = excepthook" in Path(launcher.__file__).read_text(encoding="utf-8"))

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
