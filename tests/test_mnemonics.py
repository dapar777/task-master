"""Podtržítkové zkratky (`&`) v hlavním i kontextovém menu.

Popisky příkazů zůstávají bez `&`; písmena přiděluje `mnemonics.assign`
najednou přes všechna menu, kde se sdílené QAction objeví, takže jsou
v každém menu jedinečná a všude stejná. Menu Filtry si přiděluje při
každé přestavbě, názvy filtrů s `&` jsou doslovné (`&&`).
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
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_mnemo_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

from app import mnemonics  # noqa: E402
from app.constants import APP_NAME, ORG_NAME, STATUSES  # noqa: E402

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


print("1) Přidělení písmen")
r = mnemonics.assign([["Nový úkol", "Nový podúkol", "Smazat úkol"]])
check("první písmeno prvního slova", r["Nový úkol"] == "&Nový úkol")
check("obsazené písmeno -> začátek dalšího slova", r["Nový podúkol"] == "Nový &podúkol")
check("další popisek", r["Smazat úkol"] == "&Smazat úkol")
r = mnemonics.assign([["Vrátit zpět", "Otevřít prostor…"], ["Vrátit zpět", "Vyjmout úkol"]])
check("sdílený popisek má jedno písmeno platné v obou menu",
      r["Vrátit zpět"] == "&Vrátit zpět" and r["Vyjmout úkol"] == "V&yjmout úkol")
r = mnemonics.assign([["Čeká", "Čeká do…", "Úkol"]])
check("diakritika až naposled (jako Ú&kol v liště)",
      r["Čeká"] == "Č&eká" and r["Čeká do…"] == "Čeká &do…" and r["Úkol"] == "Ú&kol")
check("strip a escape", mnemonics.strip("&Nový && spol") == "Nový & spol"
      and mnemonics.escape("A & B") == "A && B" and mnemonics.strip("A && B") == "A & B")
r = mnemonics.assign([["A && B", "Alfa"]])
check("doslovný && zůstane a mnemonika je jinde",
      "&&" in r["A && B"] and mnemonics.mnemonic_char(r["A && B"]) in ("a", "b")
      and mnemonics.strip(r["A && B"]) == "A & B")
r = mnemonics.assign([["&Hotovo", "Hlavní"]])
check("hotová mnemonika zůstane a písmeno je obsazené", r["&Hotovo"] == "&Hotovo" and r["Hlavní"] == "H&lavní")
r = mnemonics.assign([["a", "b", "a b"]])
check("bez volného písmene zůstane popisek bez &", r["a b"] == "a b" and r["a"] == "&a" and r["b"] == "&b")
check("mnemonic_char", mnemonics.mnemonic_char("Nový &podúkol") == "p" and mnemonics.mnemonic_char("bez") == ""
      and not mnemonics.has_mnemonic("A && B"))

# --- okno: MainWindow čte QSettings(ORG_NAME, APP_NAME) natvrdo – přesměruj a vrať
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
_s.setValue("workspace", str(tmp))
_s.setValue("view_mode", "tree")
_s.setValue("mail_interval_min", 0)
_s.sync()

from app import mailimport, theme  # noqa: E402

mailimport._cred_read = lambda: None

from app.mainwindow import MainWindow  # noqa: E402
from app.savedfilters import SavedFilter  # noqa: E402
from app.shortcuts import COMMAND_DEFS  # noqa: E402
from app.storage import Workspace  # noqa: E402

ws = Workspace(tmp)
ws.load()
ws.create_root("Alfa")
ws.load()

theme.apply(app, "light", zoom=1.0)
win = MainWindow()
atexit.register(lambda: (win.close(), win.deleteLater()))
win._import_mail_auto = lambda: None
win.filter_store.filters.clear()  # test nesmí záviset na reálných uložených filtrech
win._rebuild_filter_menu()


def items_of(menu: QMenu):
    return [a for a in menu.actions() if not a.isSeparator()]


def unique_mnemonics(actions) -> tuple[bool, list[str]]:
    chars = [mnemonics.mnemonic_char(a.text()) for a in actions]
    return (all(chars) and len(set(chars)) == len(chars)), chars


print("2) Menu v liště: každá položka má podtržítko, v jednom menu se neopakují")
menus = {m.title(): m for m in win.menuBar().findChildren(QMenu) if m.title()}
for title in ("&Soubor", "Ú&kol", "&Zobrazení", "&Filtry", "&Editor", "&Nastavení"):
    ok, chars = unique_mnemonics(items_of(menus[title]))
    check(f"{mnemonics.strip(title)}: {''.join(chars)}", ok)
check("podnabídka Stav v Úkolu má podtržítko", mnemonics.has_mnemonic(win._m_status.title())
      and mnemonics.strip(win._m_status.title()) == "Stav")

print("3) Kontextové menu stromu, karty a podnabídka Stav")
node = win.workspace.roots[0]
win._current_node = node
tree_labels = [win.act[c].text() for c in win.TREE_MENU_CIDS if c] + [win._mn(win.STATUS_MENU_TITLE)]
chars = [mnemonics.mnemonic_char(t) for t in tree_labels]
check(f"strom: {''.join(chars)}", all(chars) and len(set(chars)) == len(chars))
card = win._build_card_menu(node)
ok, chars = unique_mnemonics(items_of(card))
check(f"karta: {''.join(chars)}", ok)
status_sub = next(a.menu() for a in card.actions() if a.menu() is not None)
ok, chars = unique_mnemonics(items_of(status_sub))
check(f"podnabídka Stav na kartě: {''.join(chars)}", ok
      and [mnemonics.strip(a.text()) for a in items_of(status_sub)] == list(STATUSES.values()))
win._fill_status_menu()
ok, chars = unique_mnemonics(items_of(win._m_status))
check("podnabídka Stav v liště stejná", ok
      and [a.text() for a in items_of(win._m_status)] == [a.text() for a in items_of(status_sub)])
card.deleteLater()

print("4) Sdílené akce: jedno písmeno všude, popisky bez & zůstávají zdrojem")
shared = [c for c in win.TREE_MENU_CIDS if c]
check("akce v liště i v kontextu mají tentýž text", all(win.act[c].text() == win.act[c].text() for c in shared)
      and all(mnemonics.has_mnemonic(win.act[c].text()) for c in shared))
check("strip(text akce) == popisek příkazu (mimo lištu editoru, kde je text glyf)",
      all(mnemonics.strip(win.act[c].text()) == win.shortcuts.label(c)
          for c in win.act if c in COMMAND_DEFS and win.shortcuts.category(c) != "Editor"))
editor_items = items_of(menus["&Editor"])
check("menu Editor ukazuje popisky příkazů, ne glyfy z lišty",
      [win._menu_label(a) for a in editor_items] == [win.shortcuts.label(c) for c in (
          "fmt.bold", "fmt.italic", "fmt.strike", "fmt.code", "fmt.h1", "fmt.h2", "fmt.h3", "fmt.paragraph",
          "fmt.bullet", "fmt.numbered", "fmt.quote", "fmt.hr", "fmt.link", "view.toggle_source")])
bold = editor_items[0]
check("zkratka editoru je ve sloupci menu (za tabulátorem), ne registrovaná podruhé",
      bold.text().split("	", 1)[1] == "Ctrl+B" and bold.shortcut().isEmpty())
check("glyf v liště editoru zůstal", win.act["fmt.bold"].text() == "B")
fired = []
win.act["fmt.bold"].triggered.connect(lambda *_: fired.append(1))
bold.trigger()
check("položka menu spustí původní akci", fired == [1])
src_proxy = editor_items[-1]
win.act["view.toggle_source"].setChecked(True)
check("zaškrtnutí se zrcadlí z originálu", src_proxy.isChecked())
win.act["view.toggle_source"].setChecked(False)
check("a zpět", not src_proxy.isChecked())
check("tooltip akce je bez &", "&" not in win.act["task.new"].toolTip())
cmds = win._build_palette_commands()
check("paleta bez podtržítek", not any(mnemonics.has_mnemonic(e["label"]) for e in cmds))
status_entry = next(e for e in cmds if e["label"] == "Stav")
kids = status_entry["children"]() if callable(status_entry["children"]) else status_entry["children"]
check("stavy v paletě bez podtržítek", kids and not any(mnemonics.has_mnemonic(k["label"]) for k in kids))

print("5) Menu Filtry: názvy doslovně, mnemoniky po každé přestavbě bez hromadění")
win.filter_store.add(SavedFilter(name="A & B", statuses=["done"], view="tree"))
win.filter_store.add(SavedFilter(name="Alfa", statuses=["todo"], view="tree"))
win._rebuild_filter_menu()
win._rebuild_filter_menu()
acts = items_of(win.m_filters)
ok, chars = unique_mnemonics(acts)
check(f"filtry: {''.join(chars)}", ok)
ab = next(a for a in acts if mnemonics.strip(a.text()) == "A & B")
check("doslovný & v názvu filtru zůstal (&&)", "&&" in ab.text() and ab.text().count("&") == 3)
check("po opakované přestavbě jen jedno podtržítko na položku",
      all(a.text().count("&") - 2 * a.text().count("&&") == 1 for a in acts))
check("Uložit/Spravovat filtr mají podtržítko",
      mnemonics.has_mnemonic(win.act["filter.save"].text()) and mnemonics.has_mnemonic(win.act["filter.manage"].text()))

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
