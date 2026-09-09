"""Tažení ven z aplikace: každý levý stisk myši v okně svolí cíli tažení převzít
popředí (`winutil.allow_foreground_change` = AllowSetForegroundWindow(ASFW_ANY)),
aby dotaz cílového programu (Total Commander: „Vložit? Ano/Ne") dostal Enter
a tažení nezůstalo viset. Pravý stisk ani kolečko svolení nedávají."""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QSettings, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_dragfocus_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

from app.constants import APP_NAME, ORG_NAME  # noqa: E402

_s = QSettings(ORG_NAME, APP_NAME)
_orig = {k: _s.value(k) for k in ("workspace", "view_mode", "mail_interval_min")}


def _restore_settings():
    s = QSettings(ORG_NAME, APP_NAME)
    for k, v in _orig.items():
        if v is None:
            s.remove(k)
        else:
            s.setValue(k, v)
    s.sync()


atexit.register(_restore_settings)
_s.setValue("workspace", str(tmp / "ws"))
_s.setValue("view_mode", "tree")
_s.setValue("mail_interval_min", 0)
_s.sync()

from app import winutil  # noqa: E402
from app.storage import Workspace  # noqa: E402

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


# 1) samotná funkce: na Windows volá user32 a vrací bool, jinde je no-op
res = winutil.allow_foreground_change()
check("allow_foreground_change vrací bool a nevyhazuje", isinstance(res, bool))
check("konstanta ASFW_ANY = -1 (kdokoli)", winutil.ASFW_ANY == -1)

# 2) průchod oknem: levý stisk kdekoli (strom, editor) svolení dává, pravý ne, kolečko ne
ws_dir = tmp / "ws"
ws = Workspace(ws_dir)
ws.load()
ws.create_root("Úkol A")
ws.create_root("Úkol B")

calls = []
winutil.allow_foreground_change = lambda: calls.append(1) or True

from app.mainwindow import MainWindow  # noqa: E402

win = MainWindow()
win.resize(1100, 700)
win.show()
QTest.qWaitForWindowExposed(win)
app.processEvents()

tree_vp = win.tree.viewport()
item = win.tree.topLevelItem(0)
pos = win.tree.visualItemRect(item).center()
calls.clear()
QTest.mouseClick(tree_vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos)
app.processEvents()
check("levý stisk ve stromu svolí převzetí popředí (1×)", calls == [1])

calls.clear()
QTest.mouseClick(tree_vp, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, pos)
app.processEvents()
check("pravý stisk svolení nedává", calls == [])

editor = win.detail.editor.edit
calls.clear()
QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(5, 5))
app.processEvents()
check("levý stisk v editoru (tažení textu) svolení dává", calls == [1])

calls.clear()
QTest.mouseMove(tree_vp, pos + QPoint(30, 0))
app.processEvents()
check("samotný pohyb myši svolení nedává", calls == [])

win.close()
print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
