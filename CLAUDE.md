# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Co to je

Desktopový hierarchický task manager pro Windows: Python 3 + PySide6 (Qt), PyYAML.
Žádná databáze, žádný web – úložiště je čistě souborový strom. Kód, komentáře,
UI, testy i commit messages jsou **česky**; commit message = jednořádkové české
shrnutí změny (viz `git log`). README.md je podrobný a aktuální – při změně
chování aktualizuj i jeho odpovídající sekci (funkce, zkratky, Výkon, tabulka testů).

## Příkazy

```bash
pip install -r requirements.txt
python main.py                      # spuštění (run.vbs / run.bat = bez konzole)
python tests/run_all.py             # všechny testy
python tests/test_snooze.py         # jeden test (každý je samostatný skript)
```

Žádný linter ani formatter není nastavený. Testy nejsou pytest: každý soubor je
skript, který tiskne `OK`/`FAIL` řádky a končí exit kódem; řádek
`SELHALO: nic – vše prošlo` je **úspěch**. Běží headless (`QT_QPA_PLATFORM=offscreen`
si nastavují samy) nad dočasným workspace.

### Psaní testů

- Nový test zaregistruj v seznamu `TESTS` v [tests/run_all.py](tests/run_all.py)
  a do tabulky testů v README.
- `MainWindow` čte `QSettings(ORG_NAME, APP_NAME)` **natvrdo** – test, který ho
  vytváří, musí klíč `workspace` (a `view_mode`) přesměrovat do temp adresáře a
  přes `atexit` vrátit původní hodnoty (vzor: `tests/test_reparent_rename.py`).
  Jinak okno otevře reálná data uživatele a přepíše v nich metadata.
- Modální dialogy se obcházejí monkeypatchem:
  `mw.TaskDialog.get = staticmethod(lambda *a, **k: vals)`.

## Architektura (to, co se nepozná z jednoho souboru)

**Úkol = adresář na disku** (`<slug>/<slug>.md` tělo + `<slug>.yaml` metadata),
podúkol = podadresář, libovolná hloubka. Kořen workspace navíc drží
`_state.yaml` (aktivní úkol, filtr, zobrazení) a `_activity.log` (JSON Lines,
formát v [app/ACTIVITY_LOG_FORMAT.md](app/ACTIVITY_LOG_FORMAT.md)).
Per-uživatelská konfigurace (zkratky, uložené filtry) je mimo workspace
v `QStandardPaths.AppConfigLocation`.

**`app/storage.py`** – `TaskNode` (uzel s `parent`/`children`, `meta` dict,
`task_id` = stabilní UUID `_id`, `title`) a `Workspace` (`roots`, `all_nodes()`,
`node_by_id()`, `load()`). Strom žije v paměti; `load()` znovu parsuje YAML jen
u uzlů se změněným otiskem a ostatní **recykluje i s cache** (`_has_body`).
Strukturální operace (přejmenování, přesun, mazání, vkládání) udržují paměťový
strom samy – **nevolej po nich `load()`**; ten patří jen tam, kde se disk mohl
změnit zvenčí (otevření prostoru, F5, undo ze zálohy).

**`app/mainwindow.py`** – `MainWindow` je imperativní Qt orchestrátor (signály/sloty,
žádný store/reducer). Klíčové body:
- `_current_node` je **property se setterem** (loguje změnu aktivního úkolu).
  Přiřazuje se na desítkách míst; „aktivní úkol" je vždy tenhle atribut.
- `_populate()` přebuduje aktuální pohled z workspace (nejdřív
  `_recompute_auto_blocks()`), pro seznam/karty přes `_flat_sequence()` – jediný
  zdroj pravdy pro pořadí v plochém pohledu (podúkoly nad rodičem via
  `sort_flat`, v kartách navíc skupiny podle stavu `_group_index`). Zařazování
  nových/přesouvaných úkolů z něj vychází, aby seděl s tím, co uživatel vidí.
- Filtr: `_match(node)` = vyhovuje filtru **nebo je aktivní** (aktivní úkol
  zůstává vidět i mimo filtr). Pro průchod přes všechny úkoly používej
  `_matcher()` / `filter_panel.matcher()` (jeden snímek filtru), ne `matches()`
  v cyklu – čtení stavu widgetů pro každý úkol bylo hlavní brzdou.
- Tři pohledy ve `QStackedWidget`: `TaskTreeWidget` (strom i seznam, signál
  `taskSelected`) a `CardView` „Bez rušení" (signál `cardSelected`). Karty se
  při přebudování recyklují podle `_card_stamp` – **cokoli, co karta vykresluje,
  musí být v otisku**, jinak se zobrazí zastaralý obsah.
- Stav se ukládá debouncovaně (`_schedule_state_save` → `_state.yaml`);
  `_snooze_timer` tiká každou sekundu a přebuduje pohled jen když nějaký
  odklad doběhl.

**Příkazová paleta = registr všech funkcí.** `MainWindow._build_palette_commands`
je **první místo**, kam patří každá nová uživatelská funkce (kategorie, popisek,
zkratka, `run`); menu a zkratky jsou jen podmnožiny. Nová funkce bez záznamu
v paletě = nedokončená; `tests/test_palette.py` hlídá, že každá akce z `self.act`
má položku. Položka s `children` (seznam nebo callable, staví se líně) otevře
další úroveň (Stav, Priorita, Odložit o, Řadit podle › pole › směr, Zobrazení,
Téma, Zoom, Filtr: …, Uložené filtry, Podúkoly, Související úkoly, Soubory
úkolu); `checked=True` označí aktuální stav; `keep_open=True` nechá paletu
otevřenou a přestaví úroveň (přepínání kritérií filtru – stav čti v callable
`children`, ne v uzávěru, jinak zaškrtnutí zastará); `search=callable(dotaz)`
je vyhledávací úroveň (Přejít na úkol), `extra_search`/`mode_search` dodávají
úkoly na kořen (3+ znaky, prefix `u `). Naposledy použité se ukládají do
QSettings `palette_recent` jako cesty popisků oddělené `|` – **přejmenování
popisku** starý záznam tiše zahodí, popisky na kořeni musí být jedinečné.
Hledání na kořeni prochází i listy podúrovní (`_deep_entries`, hloubka 3).

**`app/undo.py`** – hybridní undo: levné záznamy (`fields`, `created`, `moved`,
`deleted`) místo kopie workspace; `snapshot` je jen fallback. Před operací,
která mění metadata více uzlů, ulož je přes `undo.push_fields(...)`.

**`app/mailimport.py`** – úkoly z e-mailu (IMAP) do kořenové sekce `_INBOX`
(`find_inbox` bere i `_Inbox`). Síť (`ImapMailbox`, `fetch_unseen`, `finish`)
běží v `MailWorker` (QThread), úkoly zakládá **hlavní vlákno** přes
`import_messages(workspace, messages)` – strom není thread-safe. Dvě fáze:
stáhnout → založit → teprve pak označit jako přečtené (schránka zůstává mezi
fázemi otevřená). Message-ID jde do meta `_mail_id` (dedup napříč celým
prostorem, Android ho zachová); přílohy do adresáře úkolu s **relativní**
`_links.path` – `TaskNode.link_path()` ji řeší vůči adresáři úkolu (detail,
paleta), absolutní cesty a URI nechává. HTML těla převádí `app/htmlmd.py`
(vlastní převodník; `QTextDocument.toMarkdown` v offscreen testech ztrácí
tučné). Heslo je ve Správci pověření (pywin32 `win32cred`, fallback QSettings);
testy používají `MailSettings.load/save(..., secure=False)` a místo sítě
monkeypatchují `mailimport.fetch_unseen` (vzor `tests/test_mail_import.py`).

**Ikona a hlavní panel** – ikona je ze sady Terakota (`assets/icons/task-master-{light,dark}.ico`,
`app/appicon.py`). Python z Microsoft Store je MSIX balíček a Windows v hlavním panelu ukazuje
logo balíčku (Python) místo ikony okna; `MainWindow.showEvent` a `_retheme_header` proto volají
`appicon.apply_taskbar_identity()`, které zapíše AppUserModel vlastnosti na HWND přes pywin32
`propsys` (bez pywin32 se tiše přeskočí, ikona okna zůstane).

**Vzhled** – `app/theme.py` je jediný zdroj barev (Solarized, světlé/tmavé
tokeny `Tokens`, `status_style()`, `priority_style()`, `title_font()`, QSS).
Nikde jinde hex barvy nepiš (`tests/test_theme.py` to hlídá; výjimka je
legacy `constants.STATUS_COLORS` pro staré testy). Ikony jsou kreslené
(`icons.icon("flag")`), ne emoji; společné prvky (Chip, StatusChip,
PriorityPill, SegmentedControl, IconButton, TitleLabel) jsou v `app/widgets.py`.
Widget, který si barvu nebo rozměr drží mimo QSS, má metodu `retheme()` – hlavní
okno ji po přepnutí tématu **i po zoomu** zavolá na všech potomcích. Obrázky pro
QSS (`url(...)`) generuje `theme._write_asset()` jako SVG do temp adresáře, ne do repa.

**Zoom** – jeden faktor `theme.zoom()` (0.7–2.0, v QSettings `zoom`). QSS
prochází `theme.scaled()` (násobí každé `Npx`/`Npt`, `1px` hranice nechává),
písma z `theme.*_font()` jdou přes `pt()`. **Pixelový rozměr v kódu piš přes
`theme.px(n)`** (okraje layoutů, `setIconSize`, prahy šířky, geometrie v
`paintEvent`) a pokud ho widget nastavuje v konstruktoru, přesuň ho do
`retheme()`, jinak po zoomu zůstane starý. `_card_stamp` obsahuje zoom, karty
se tedy po zoomu přestaví; strom si výšky řádků bere z delegáta přes `px()`.
Zoom mění hlavní okno v `_apply_zoom()` → `theme.apply(..., zoom=)` +
`icons.clear_cache()` + `_retheme()`; `Ctrl+kolečko` chytá `eventFilter`
nainstalovaný na `QApplication` (i nad editorem).

**Úzké okno** (jde zúžit na ~350 px) – tři nezávislé prahy, každý ve své třídě:
`MainWindow.HEADER_COMPACT_BELOW` (hlavička jen s ikonami),
`CardView.NARROW_BELOW` (pravý shluk karty pod název; `_narrow` je součástí
`_card_stamp`) a `TaskTreeWidget._fit_columns()` (nejdřív se zužuje sloupec
Stav, pak Priorita, Úkol až naposled). Široké popisky mají
`QSizePolicy.Ignored` vodorovně a karty nesmí sloupci diktovat minimum – nový
widget v hlavičce, detailu či kartě, který má pevnou šířku, celé okno zase
„zamkne" na širší minimum.

## Invarianty, které se snadno rozbijí

- **`_order` je float a musí být jedinečné GLOBÁLNĚ** (napříč celým stromem, ne
  jen mezi sourozenci či viditelnými). Kolize spustí `normalize_orders()`, která
  přečísluje a **uloží všechny úkoly** (sekundy) a zneplatní otisky karet.
  Nové pořadí získávej přes `workspace.next_order()` nebo `MainWindow._order_between()`
  (počítá vůči všem obsazeným hodnotám); podúkoly tvoř přes
  `workspace.create_child_of()`, ne `TaskNode.create_child()` přímo.
- Widgety karet vytvářej **s rodičem** (`parent=self.container`) a plnění s
  vypnutými aktualizacemi – jinak Qt kartu na okamžik ukáže jako samostatné okno.
- Stav `snoozed` s doběhlým odpočtem (`snooze_elapsed()`) se ve filtru, řazení
  i auto-blokaci chová jako `todo`, dokud odpočet běží jako `waiting` – při
  úpravách stavové logiky ověř obě větve (viz `tests/test_snooze.py`).
- `_status == "blocked"` s `_auto_blocked: True` spravuje automat
  (`_recompute_auto_blocks`); ruční blokování má příznak False a nesmí se přepsat.
