"""Editor popisu nad Milkdown (QtWebEngine): načtení bundlu, most QWebChannel,
set/to_markdown, hlášení změn, zdrojový režim, volba enginu a fallback na Qt.

Bez QtWebEngine (PySide6-Addons) nebo bez sestaveného bundlu se test přeskočí
s hláškou – aplikace v takovém případě sama použije QTextEdit editor.
"""
import atexit
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox --disable-dev-shm-usage")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication, QSettings, Qt  # noqa: E402

# WebEngine musí být importovaný před vznikem QApplication (sdílené GL kontexty)
try:
    import PySide6.QtWebEngineWidgets  # noqa: E402,F401
    HAVE_WEBENGINE = True
except ImportError:
    HAVE_WEBENGINE = False
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from app import theme, webeditor  # noqa: E402
from app.editor import MarkdownEditor  # noqa: E402

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


def wait_until(pred, timeout=20.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if pred():
            return True
        time.sleep(0.01)
    return False


def js(ed, code):
    """Spustí JS ve stránce a počká na výsledek (runJavaScript je asynchronní)."""
    box = {}
    ed.view.page().runJavaScript(code, 0, lambda r: box.__setitem__("r", r))
    wait_until(lambda: "r" in box, 10.0)
    return box.get("r")


print("1) Volba enginu a fallback")
tmp = Path(tempfile.mkdtemp(prefix="tm_webed_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))
s = QSettings(str(tmp / "s.ini"), QSettings.Format.IniFormat)
check("výchozí engine je Milkdown", webeditor.configured_engine(s) == webeditor.ENGINE_MILKDOWN)
s.setValue("editor_engine", "qt")
check("volba qt se respektuje", webeditor.configured_engine(s) == webeditor.ENGINE_QT)
s.setValue("editor_engine", "nesmysl")
check("neznámá hodnota -> výchozí", webeditor.configured_engine(s) == webeditor.ENGINE_MILKDOWN)
s.setValue("editor_engine", "qt")
check("engine qt dá MarkdownEditor", isinstance(webeditor.create_editor(settings=s), MarkdownEditor))
s.setValue("editor_engine", "milkdown")
orig = webeditor.webengine_available
webeditor.webengine_available = lambda: False
check("bez WebEngine fallback na MarkdownEditor", isinstance(webeditor.create_editor(settings=s), MarkdownEditor))
webeditor.webengine_available = orig

if not (HAVE_WEBENGINE and webeditor.BUNDLE.is_file()):
    why = "QtWebEngine není nainstalovaný" if not HAVE_WEBENGINE else f"chybí bundle {webeditor.BUNDLE}"
    print(f"\nPŘESKOČENO: {why} – zbytek testu vyžaduje Milkdown editor")
    print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
    sys.exit(1 if fails else 0)

print("2) Načtení a most")
ed = webeditor.create_editor(settings=s)
check("engine milkdown dá MilkdownEditor", isinstance(ed, webeditor.MilkdownEditor))
ed.resize(600, 400)
ed.show()
check("stránka ohlásí onReady", wait_until(ed.is_ready, 30.0))
if ed.console_messages:
    print("   JS konzole:", *ed.console_messages[:5], sep="\n     ")
check("stránka hlásí TM.isReady()", js(ed, "window.TM.isReady()") is True)
check("TMHost je navázaný přes QWebChannel", js(ed, "typeof window.TMHost === 'object' && window.TMHost !== null") is True)
check("stejná sada příkazů jako Qt editor",
      set(ed.command_actions) == set(MarkdownEditor().command_actions))

print("3) Obsah tam a zpět")
md = "# Nadpis\n\nOdstavec s **tučným** a *kurzívou*.\n\n* první\n* druhá\n"
changes = []
ed.contentChanged.connect(lambda: changes.append(1))
ed.set_markdown(md)
check("set_markdown nehlásí změnu", wait_until(lambda: js(ed, "window.TM.getMarkdown()") != "", 10.0) and not changes)
page_md = js(ed, "window.TM.getMarkdown()")
check("stránka drží tučné i kurzívu", "**tučným**" in page_md and ("*kurzívou*" in page_md or "_kurzívou_" in page_md))
check("stránka drží nadpis a seznam", page_md.startswith("# Nadpis") and "první" in page_md)
check("to_markdown vrací, co se vložilo", ed.to_markdown() == md)

print("4) Změna ve stránce dorazí do Pythonu")
js(ed, "window.TM.insertText('AHOJ')")
check("onChange -> contentChanged", wait_until(lambda: bool(changes), 10.0))
check("to_markdown obsahuje nový text", wait_until(lambda: "AHOJ" in ed.to_markdown(), 10.0))

print("5) Zdrojový režim")
ed.source_action.setChecked(True)
check("zdroj ukazuje aktuální markdown", "AHOJ" in ed.source_edit.toPlainText() and ed.edit is ed.source_edit)
check("formátovací akce jsou vypnuté", all(not a.isEnabled() for a in ed._format_actions))
ed.source_edit.setPlainText("## Jen zdroj\n\ntext")
check("to_markdown ve zdroji = text pole", ed.to_markdown() == "## Jen zdroj\n\ntext")
ed.source_action.setChecked(False)
check("návrat propíše zdroj do stránky",
      wait_until(lambda: js(ed, "window.TM.getMarkdown()").startswith("## Jen zdroj"), 10.0) and ed.edit is ed.view)

print("6) Téma do stránky")
ed.retheme()
vars_ = webeditor.theme_vars()


def rgb(hex_):
    h = hex_.lstrip("#")
    return f"rgb({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)})"


# měřit na `.milkdown`, ne na <html>: téma Crepe definuje proměnné právě tam a přebilo by je
on_editor = js(ed, "getComputedStyle(document.querySelector('.milkdown')).getPropertyValue('--crepe-color-background').trim()")
check("--crepe-color-background na .milkdown je z theme.py", on_editor.lower() == vars_["--crepe-color-background"].lower())
body_bg = js(ed, "getComputedStyle(document.body).backgroundColor")
check("skutečné pozadí stránky = plátno tématu", body_bg == rgb(vars_["--crepe-color-background"]))
text_color = js(ed, "getComputedStyle(document.querySelector('.milkdown .ProseMirror')).color")
check("barva textu editoru = text tématu", text_color == rgb(vars_["--crepe-color-on-background"]))
check("velikost písma jde přes zoom (px)", js(ed, "getComputedStyle(document.querySelector('.milkdown')).getPropertyValue('--tm-font-size').trim()").endswith("px"))
# tmavé téma: po přepnutí tokenů se stránka přebarví (bez reloadu)
theme.apply(app, "dark", zoom=theme.zoom())
ed.retheme()
dark = webeditor.theme_vars()
check("tmavé téma se liší od světlého", dark["--crepe-color-background"] != vars_["--crepe-color-background"])
check("po přepnutí na tmavé má stránka tmavé plátno",
      wait_until(lambda: js(ed, "getComputedStyle(document.body).backgroundColor") == rgb(dark["--crepe-color-background"]), 5.0))
theme.apply(app, "light", zoom=theme.zoom())
ed.retheme()
pad_bottom = js(ed, "getComputedStyle(document.querySelector('.milkdown .ProseMirror')).paddingBottom")
check(f"spodní odsazení editoru je malé, ne desetiny okna ({pad_bottom})",
      pad_bottom.endswith("px") and float(pad_bottom[:-2]) <= 48)

print("7) Bez & v popiscích, bez chyb v konzoli")
check("JS konzole bez chyb", not any("error" in m.lower() for m in ed.console_messages))
check("popisky lišty bez &", all("&" not in a.text() for a in ed.command_actions.values()))

print("8) Ukončení procesu (QtWebEngine padá při špatném pořadí úklidu)")
import subprocess  # noqa: E402

ROOT = str(Path(__file__).resolve().parent.parent)
PRELUDE = (
    "import os, sys\n"
    "os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')\n"
    "os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu --no-sandbox --disable-dev-shm-usage')\n"
    f"sys.path.insert(0, {ROOT!r})\n"
)
# jako main.py: WebEngine před QApplication, editor se použije a proces končí čistě
APP_LIKE = PRELUDE + (
    "from PySide6.QtCore import QCoreApplication, Qt, QTimer\n"
    "import PySide6.QtWebEngineWidgets\n"
    "QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)\n"
    "from PySide6.QtWidgets import QApplication\n"
    "app = QApplication([])\n"
    "from app import webeditor\n"
    "ed = webeditor.MilkdownEditor(); ed.show()\n"
    "box = {'ok': False}\n"
    "def tick():\n"
    "    if ed.is_ready(): ed.set_markdown('x'); box['ok'] = True; app.quit()\n"
    "t = QTimer(); t.timeout.connect(tick); t.start(50)\n"
    "QTimer.singleShot(25000, app.quit)\n"
    "app.exec()  # aboutToQuit -> ed.shutdown() (is_ready() je pak už False)\n"
    "ed.close(); ed.deleteLater(); webeditor.drain_deferred(app)\n"
    "sys.exit(0 if box['ok'] else 2)\n"
)
# jako běžný test: QApplication dřív než WebEngine -> create_editor dá Qt editor a proces končí čistě
LATE_IMPORT = PRELUDE + (
    "from PySide6.QtWidgets import QApplication\n"
    "app = QApplication([])\n"
    "from app import webeditor\n"
    "from app.editor import MarkdownEditor\n"
    "ed = webeditor.create_editor()\n"
    "sys.exit(0 if isinstance(ed, MarkdownEditor) and not webeditor.webengine_available() else 3)\n"
)
for label, code in (("aplikace s Milkdownem končí s exit 0", APP_LIKE),
                    ("pozdní import WebEngine -> Qt editor, exit 0", LATE_IMPORT)):
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    check(f"{label} (bylo {r.returncode})", r.returncode == 0)
    if r.returncode != 0:
        print("   stderr:", (r.stderr or "")[-600:])

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
ed.close()
ed.shutdown()
ed.deleteLater()
webeditor.drain_deferred(app)
sys.exit(1 if fails else 0)
