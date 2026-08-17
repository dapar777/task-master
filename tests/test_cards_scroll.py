"""Bez rušení: přebudování karet nesmí srazit pohled nahoru.

Nahoru se skáče JEN když změna stavu odsune aktivní kartu do nižší
skupiny. Editace názvu, změna metadat ani přidání úkolu pohled nehýbou.
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
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_cards_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

from app.constants import APP_NAME, ORG_NAME  # noqa: E402

# MainWindow si dělá QSettings(ORG_NAME, APP_NAME) natvrdo – původní
# hodnoty proto zapamatuj a vždy vrať, ať nepřepíšeme nastavení uživatele.
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
_s.setValue("view_mode", "cards")
_s.sync()

from app.mainwindow import MainWindow  # noqa: E402
from app.storage import Workspace  # noqa: E402

ws = Workspace(tmp)
ws.load()
for i in range(14):  # dost karet, ať je co rolovat
    ws.create_root(f"Ukol {i:02d}")
ws.load()

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


win = MainWindow()
win.resize(1100, 650)
win.show()
QTest.qWaitForWindowExposed(win)
app.processEvents()

cv = win.card_view


def settle():
    app.processEvents()
    QTest.qWait(80)
    app.processEvents()


def scroll():
    return cv.verticalScrollBar().value()


def node(title):
    return next((n for n in win.workspace.all_nodes() if n.title == title), None)


def focus_on(title):
    n = node(title)
    win._current_node = n
    win._select_in_view(n)
    settle()
    return n


# odroluj doprostřed a stůj na kartě, která je vidět
target = focus_on("Ukol 08")
cv.verticalScrollBar().setValue(cv.verticalScrollBar().maximum() // 2)
settle()
base = scroll()
if base == 0:
    print("  SKIP  pohled se nedá odrolovat (malý rozsah)")
    sys.exit(0)
print(f"výchozí pozice rolování: {base}")

print("1) EDITACE názvu aktivní karty pohled nehýbe")
win._on_rename(target, "Ukol 08 prejmenovany")
settle()
check(f"scroll zůstal ({base} -> {scroll()})", scroll() == base)
check("aktivní je pořád tentýž úkol",
      win._current_node is not None
      and win._current_node.title == "Ukol 08 prejmenovany")

print("2) ZMĚNA METADAT (priorita) pohled nehýbe")
cur = win._current_node
cur.set_field("_priority", 9)
win._on_meta_changed(cur)
settle()
check(f"scroll zůstal ({base} -> {scroll()})", scroll() == base)

print("3) PŘIDÁNÍ úkolu samo o sobě pohled nesráží nahoru")
win.workspace.create_root("Zbrusu novy")
win.workspace.load()
win._populate()
settle()
check(f"scroll zůstal ({base} -> {scroll()})", scroll() == base)

print("4) ZMĚNA STAVU JINÉ karty pohled nepřehazuje")
other = node("Ukol 02")
win._apply_status_to([other], "done")
settle()
check(f"scroll zůstal ({base} -> {scroll()})", scroll() == base)
check("aktivní karta se nezměnila",
      win._current_node is not None
      and win._current_node.title == "Ukol 08 prejmenovany")

print("5) ZMĚNA STAVU AKTIVNÍ karty (spadne do nižší skupiny) -> skok nahoru")
win._apply_status_to([win._current_node], "done")
settle()
check(f"pohled odrolován nahoru (scroll={scroll()})", scroll() == 0)
if cv._order:
    check("aktivní je první karta shora",
          win._current_node is not None
          and str(win._current_node.path) == cv._order[0])

def active_visible() -> bool:
    """Je aktivní karta vidět ve výřezu? (přesnou pozici porovnávat nelze –
    select_path k aktivní kartě legitimně odroluje)"""
    card = cv._cards.get(cv._focus)
    if card is None:
        return False
    sb = cv.verticalScrollBar()
    return (card.y() + card.height() > sb.value()
            and card.y() < sb.value() + cv.viewport().height())


print("6) VÍCEVÝBĚR bez aktivní karty nepřehodí výběr ani neskočí nahoru")
focus_on("Ukol 05")
settle()
win._apply_status_to([node("Ukol 11"), node("Ukol 12")], "done")
settle()
check("aktivní karta se nezměnila",
      win._current_node is not None and win._current_node.title == "Ukol 05")
check(f"aktivní karta zůstala vidět (scroll={scroll()})", active_visible())

print("7) ODŠKRTNUTÍ (posun NAHORU do vyšší skupiny) nepřehodí na první kartu")
done_node = focus_on("Ukol 06")
win._apply_status_to([done_node], "done")
settle()
back = focus_on("Ukol 06")  # postav se znovu na dokončený úkol
settle()
win._apply_status_to([back], "todo")
settle()
check("aktivní zůstala na 'Ukol 06' (neskočilo na první kartu)",
      win._current_node is not None and win._current_node.title == "Ukol 06")
check(f"aktivní karta zůstala vidět (scroll={scroll()})", active_visible())

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
win.close()
sys.exit(1 if fails else 0)
