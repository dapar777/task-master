"""Nastavení: jeden dialog (sekce vlevo, hledání), aplikace hodnot, přepínání z palety.

Dialog jen sbírá hodnoty; promítá je `MainWindow._apply_settings` přes akce
(menu + hlavička + QSettings zůstávají v synchronu). Totéž jde z palety
(kategorie „Nastavení“ s keep_open). Vlastní dialogy e-mailu a zkratek
zůstávají použitelné samostatně.
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMenu  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_settings_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

from app.constants import APP_NAME, DEFAULT_SNOOZE, ORG_NAME  # noqa: E402

# MainWindow čte QSettings(ORG_NAME, APP_NAME) natvrdo – přesměruj a po testu vrať
KEYS = ("workspace", "view_mode", "theme", "zoom", "compact_cards",
        "snooze_d", "snooze_h", "snooze_m", "palette_recent", "geometry",
        "mail_host", "mail_port", "mail_ssl", "mail_user", "mail_folder",
        "mail_interval_min", "mail_password")
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
_s.setValue("theme", "light")
_s.setValue("compact_cards", True)
_s.setValue("mail_interval_min", 0)  # reálné nastavení nesmí spustit kontrolu schránky
for k in ("zoom", "snooze_d", "snooze_h", "snooze_m", "palette_recent", "geometry", "mail_password"):
    _s.remove(k)
_s.sync()

# Správce pověření Windows nesmí dostat testovací heslo
from app import mailimport, theme  # noqa: E402

mailimport._cred_write = lambda user, pw: False
mailimport._cred_read = lambda: None

from app.mainwindow import MainWindow  # noqa: E402
from app.settingsdialog import SECTIONS, SettingsDialog  # noqa: E402
from app.search import fold  # noqa: E402
from app import mnemonics  # noqa: E402
from app.shortcuts import COMMAND_DEFS  # noqa: E402

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


theme.apply(app, "light", zoom=1.0)
win = MainWindow()
atexit.register(lambda: (win.close(), win.deleteLater()))
win.resize(1000, 650)
win.show()
QTest.qWaitForWindowExposed(win)
app.processEvents()
# automatická kontrola schránky by po 4 s sáhla na síť – v testu ji vypni
win._import_mail_auto = lambda: None

print("1) Dialog: sekce, otevření na požadované stránce, vykreslení")
d = SettingsDialog(win, "mail")
d.show()
app.processEvents()
check("má všechny sekce", d.nav.count() == len(SECTIONS) and set(d._pages) == {k for k, _, _ in SECTIONS})
check("otevřel se na sekci E-mail", d.current_section() == "mail")
check("vykreslí se", d.grab().width() > 50)
d.select_section("appearance")
check("přepnutí sekce mění stránku", d.current_section() == "appearance"
      and d.stack.currentIndex() == d._pages["appearance"])
d.select_section("neexistuje")
check("neznámá sekce padne na první", d.current_section() == SECTIONS[0][0])

print("2) Hodnoty ve formuláři odpovídají stavu aplikace")
v = d.values()
check("téma světlé", v["theme"] == "light")
check("zoom 100 %", abs(v["zoom"] - 1.0) < 1e-6)
check("úsporné karty zapnuté", v["compact_cards"] is True)
check("odklad z okna", tuple(v["snooze"]) == tuple(win._last_snooze) == tuple(DEFAULT_SNOOZE))
check("prostor = otevřený prostor", v["workspace"] == Path(win.workspace.root))
check("e-mail z okna", v["mail"].host == win.mail_settings.host
      and v["mail"].interval_min == win.mail_settings.interval_min)
check("údržba vypnutá", not v["clear_palette_recent"] and not v["reset_geometry"])
check("souhrn odkladu ukazuje délku", "10 min" in d.snooze_summary.text())
d.snooze_minutes.setValue(0)
check("nulový odklad varuje", "aspoň minutu" in d.snooze_summary.text())

print("3) Změna a uložení: promítne se do akcí, theme, QSettings i časovačů")
win.settings.setValue("palette_recent", ["Stav|Čeká"])
d.theme_seg.set_current("dark")
d.zoom_slider.setValue(125)
check("popisek zoomu sleduje posuvník", d.zoom_value.text() == "125 %")
d.compact_check.setChecked(False)
d.snooze_days.setValue(0)
d.snooze_hours.setValue(1)
d.snooze_minutes.setValue(30)
d.mail_form.host.setText("imap.example")
d.mail_form.user.setText("u")
d.mail_form.password.setText("x")
d.mail_form.interval.setValue(5)
d.clear_recent_check.setChecked(True)
d.reset_geometry_check.setChecked(True)
vals = d.values()
d.close()
win._apply_settings(vals)
app.processEvents()
check("téma přepnuté na tmavé", theme.is_dark() and win.settings.value("theme", type=str) == "dark")
check("akce tmavého tématu zaškrtnutá", win.act["view.dark_theme"].isChecked())
check("zoom 125 %", abs(theme.zoom() - 1.25) < 1e-6
      and abs(float(win.settings.value("zoom", type=float)) - 1.25) < 1e-6)
check("úsporné karty vypnuté (i akce)", win._compact_cards is False
      and not win.act["view.compact_cards"].isChecked()
      and win.settings.value("compact_cards", type=bool) is False)
check("výchozí odklad 1 h 30 min", win._last_snooze == (0, 1, 30)
      and int(win.settings.value("snooze_h", type=int)) == 1
      and int(win.settings.value("snooze_m", type=int)) == 30)
check("e-mail uložen a kontrola běží po 5 min", win.mail_settings.interval_min == 5
      and win.mail_settings.complete and win._mail_timer.isActive()
      and win._mail_timer.interval() == 5 * 60 * 1000)
check("naposledy použité v paletě smazané", win.settings.value("palette_recent") in (None, [], ""))
check("geometrie se při zavření neuloží", win._skip_geometry_save is True)
check("stavový řádek potvrdí", "Nastavení uloženo" in win.status.currentMessage())

print("4) Beze změny se nic nepřestylovává (stejné hodnoty = žádná práce)")
rebuilds = {"n": 0}
_orig_pop = type(win)._populate
type(win)._populate = lambda self: (rebuilds.__setitem__("n", rebuilds["n"] + 1), _orig_pop(self))[1]
try:
    win._apply_settings(dict(vals, clear_palette_recent=False, reset_geometry=False))
    app.processEvents()
    check(f"stejné hodnoty nepřebudují zobrazení ({rebuilds['n']})", rebuilds["n"] == 0)
finally:
    type(win)._populate = _orig_pop

print("5) Nastavení z palety")
cmds = win._build_palette_commands()
top = {e["label"]: e for e in cmds}
for lbl in ("Nastavení…", "Nastavení: výchozí odklad", "Nastavení: kontrola e-mailu",
            "Nastavení e-mailu…", "Klávesové zkratky…", "Téma", "Zoom"):
    check(f"paleta má „{lbl}“", lbl in top)
check("položky nastavení jsou v kategorii Nastavení",
      all(top[l]["category"] == "Nastavení" for l in ("Nastavení…", "Nastavení: výchozí odklad",
                                                     "Nastavení: kontrola e-mailu")))
kids = top["Nastavení: výchozí odklad"]["children"]()
check("předvolby odkladu drží keep_open a značí aktuální",
      kids and all(k.get("keep_open") for k in kids)
      and sum(1 for k in kids if k.get("checked")) == 0)  # 1 h 30 min není mezi předvolbami
next(k for k in kids if k["label"] == "1 hodina")["run"]()
check("předvolba nastaví výchozí odklad", win._last_snooze == (0, 1, 0)
      and int(win.settings.value("snooze_h", type=int)) == 1
      and int(win.settings.value("snooze_m", type=int)) == 0)
kids = top["Nastavení: výchozí odklad"]["children"]()
check("po změně je zaškrtnutá právě „1 hodina“",
      [k["label"] for k in kids if k.get("checked")] == ["1 hodina"])

kids = top["Nastavení: kontrola e-mailu"]["children"]()
check("intervaly e-mailu: aktuálních 5 min zaškrtnuto",
      [k["label"] for k in kids if k.get("checked")] == ["Každých 5 minut"]
      and all(k.get("keep_open") for k in kids))
next(k for k in kids if k["label"] == "Každých 15 minut")["run"]()
check("15 minut: uloženo a časovač přenastaven", win.mail_settings.interval_min == 15
      and int(win.settings.value("mail_interval_min", type=int)) == 15
      and win._mail_timer.isActive() and win._mail_timer.interval() == 15 * 60 * 1000)
next(k for k in kids if k["label"] == "Vypnuto (jen ručně)")["run"]()
check("vypnuto: časovač stojí", win.mail_settings.interval_min == 0 and not win._mail_timer.isActive())
check("stavový řádek hlásí interval", "Kontrola e-mailu" in win.status.currentMessage())

print("6) Otevření dialogu z akcí a menu")
_orig_exec = QDialog.exec
atexit.register(lambda: setattr(QDialog, "exec", _orig_exec))
opened = {"section": None}


def _fake_exec(self):
    if isinstance(self, SettingsDialog):
        opened["section"] = self.current_section()
    self.show()
    app.processEvents()
    self.close()
    return 0  # Zrušit


QDialog.exec = _fake_exec
check("Nastavení… (Zrušit) nic nemění", win._open_settings() is False and opened["section"] == "appearance")
win.act["app.shortcuts"].trigger()
check("Klávesové zkratky… otevře sekci Zkratky", opened["section"] == "shortcuts")
check("Nastavení e-mailu… otevře sekci E-mail a po Zrušit vrátí False",
      win._open_mail_settings() is False and opened["section"] == "mail")
check("zkratka Ctrl+, patří Nastavení…", win.act["app.settings"].shortcut().toString() == "Ctrl+,")
m_settings = next(m for m in win.menuBar().findChildren(QMenu) if m.title() == "&Nastavení")
labels = [mnemonics.strip(a.text()) for a in m_settings.actions() if not a.isSeparator()]
check("menu Nastavení začíná dialogem a má e-mail i zkratky",
      labels[0] == "Nastavení…" and "Nastavení e-mailu…" in labels and "Klávesové zkratky…" in labels)
m_file = next(m for m in win.menuBar().findChildren(QMenu) if m.title() == "&Soubor")
check("menu Soubor už nastavení e-mailu nemá",
      "Nastavení e-mailu…" not in [mnemonics.strip(a.text()) for a in m_file.actions()])
QDialog.exec = _orig_exec

print("7) Uložit z dialogu přes _open_settings")
_orig_get = SettingsDialog.get
SettingsDialog.get = staticmethod(lambda w, section=None: dict(
    theme="light", zoom=1.0, compact_cards=True, snooze=(0, 0, 10),
    mail=w.mail_settings, workspace=None, clear_palette_recent=False, reset_geometry=False))
try:
    check("Uložit vrátí True a hodnoty se aplikují",
          win._open_settings() is True and not theme.is_dark() and abs(theme.zoom() - 1.0) < 1e-6
          and win._compact_cards is True and win._last_snooze == (0, 0, 10))
finally:
    SettingsDialog.get = _orig_get

print("8) Zkratky uvnitř dialogu a samostatné dialogy")
d = SettingsDialog(win, "shortcuts")
d.show()
app.processEvents()
check("editor zkratek je naplněný", d.shortcut_editor.tree.topLevelItemCount() > 0
      and not d.shortcut_editor.is_dirty())
d.accept()
check("Uložit bez změn zkratek dialog zavře", d.result() == QDialog.DialogCode.Accepted)

from app.maildialog import MailSettingsDialog  # noqa: E402
from app.shortcutdialog import ShortcutDialog  # noqa: E402

md = MailSettingsDialog(win.mail_settings, win)
check("samostatný dialog e-mailu vrací hodnoty", md.values().host == win.mail_settings.host)
md.close()
sd = ShortcutDialog(win.shortcuts, win)
check("samostatný dialog zkratek drží strom", sd.tree.topLevelItemCount() > 0)
sd.close()

print("9) Hledání v dialogu (Ctrl+F): sekce, zvýraznění, zkratky, Enter, Esc")
d = SettingsDialog(win)
d.show()
app.processEvents()
check("po otevření má fokus hledání", d.focusWidget() is d.search)


def nav_visible():
    return [str(d.nav.item(i).data(Qt.ItemDataRole.UserRole))
            for i in range(d.nav.count()) if not d.nav.item(i).isHidden()]


def shortcut_rows_visible():
    rows = []
    for i in range(d.shortcut_editor.tree.topLevelItemCount()):
        cat = d.shortcut_editor.tree.topLevelItem(i)
        if cat.isHidden():
            continue
        rows += [cat.child(j).text(0) for j in range(cat.childCount()) if not cat.child(j).isHidden()]
    return rows


d.search.setText("imap")
check("„imap“ nechá jen sekci E-mail a přepne na ni", nav_visible() == ["mail"] and d.current_section() == "mail")
check("server je zvýrazněný", d.mail_form.host.property("searchHit") is True)
check("stav hlásí počet sekcí", d.search_status.text() == "1 sekce s nálezem.")
d.search.setText("tema")
check("bez diakritiky najde Téma ve Vzhledu", "appearance" in nav_visible() and d.current_section() == "appearance"
      and d.theme_seg.property("searchHit") is True)
check("předchozí nález se odznačil", not d.mail_form.host.property("searchHit"))
d.search.setText("kontrola mail")
check("víc slov: interval kontroly e-mailu", d.current_section() == "mail"
      and d.mail_form.interval.property("searchHit") is True)
d.search.setText("odklad")
vis = nav_visible()
rows = shortcut_rows_visible()
check("„odklad“ najde sekci Odklad i příkaz ve Zkratkách",
      "snooze" in vis and "shortcuts" in vis and "mail" not in vis and "workspace" not in vis)
check("strom zkratek ukazuje jen příkazy s odkladem", rows and all("odklad" in fold(t) for t in rows))
check("v Odkladu jsou zvýrazněné dny/hodiny/minuty", d.snooze_days.property("searchHit") is True)
d.search.setText("xyzqv")
check("nic nenalezeno: sekce zůstanou, hlášení, nic zvýrazněné",
      len(nav_visible()) == len(SECTIONS) and "Nic nenalezeno" in d.search_status.text() and not d._hits)
check("strom zkratek je při nenalezení prázdný", not shortcut_rows_visible())
d.search.setText("heslo")
QTest.keyClick(d.search, Qt.Key.Key_Return)
check("Enter dá fokus na první nález (heslo e-mailu) a nestiskne Uložit",
      d.focusWidget() is d.mail_form.password and d.isVisible())
d.search.setFocus()
QTest.keyClick(d.search, Qt.Key.Key_Escape)
check("Esc vyčistí hledání, dialog zůstane a vše se vrátí",
      d.search.text() == "" and d.isVisible() and len(nav_visible()) == len(SECTIONS) and not d._hits
      and d.search_status.text() == "" and len(shortcut_rows_visible()) == len(COMMAND_DEFS))
QTest.keyClick(d.search, Qt.Key.Key_Escape)
check("Esc v prázdném hledání dialog zavře", not d.isVisible())
d.deleteLater()

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
