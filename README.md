# Task Master

Desktopový **hierarchický task manager** pro Windows (Python + PySide6) s **WYSIWYG markdown editorem**.

## Funkce

- 🌳 **Hierarchické úkoly** – podúkoly se ukládají jako podsložky.
- 📝 **WYSIWYG markdown editor** – tučné, kurzíva, nadpisy, seznamy, citace, kód, odkazy; přepínání na zdrojový markdown.
- 🗂 **Ukládání na disk** ve formátu složek (viz níže), metadata v YAML.
- ⌨️ **Příkazová paleta** (`Ctrl+Shift+P`) – vyhledávání a spouštění všech příkazů i uložených filtrů.
- ✏️ **Inline přejmenování** – název se edituje přímo v položce stromu (`F2`), žádný dialog.
- 📋 **Schránka úkolů** – kopírovat / vyjmout / vložit (`Ctrl+C` / `X` / `V`) včetně celého podstromu; pravým tlačítkem kontextové menu.
- 📥 **Vložení z textu** (`Ctrl+Shift+V`) – odsazený text ze schránky se převede na strukturu úkolů; dialog se zeptá kam (pod / za aktuální / na konec).
- ➕ **Nový úkol** (`Ctrl+N`) vzniká jako **sourozenec** aktuálního, **podúkol** (`Ctrl+Shift+N`) pod aktuálním – přes **dialog s metadaty** (i s klávesovými zkratkami `Ctrl+T` / `Ctrl+↑↓`); kategorie a priorita se **dědí** od nadřazeného úkolu. Zařazení do pořadí respektuje zobrazení:
  - **strom** – nový úkol hned **za** aktuální; podúkol **na konec** seznamu podúkolů daného úkolu (i těch neviditelných);
  - **seznam / Bez rušení** – nový úkol **pod** aktuální; podúkol **za poslední** viditelný podúkol daného úkolu, a nejsou-li žádné ve výběru, **hned nad** aktuální úkol.
  - **Dědění** – nový úkol zdědí od nadřazeného úkolu **prioritu, vlaječku a kategorii**; z „sekčního" rodiče, jehož **název začíná podtržítkem**, se nedědí nic.
  - **Výběr umístění** – v dialogu je rozbalovací pole *Umístění* (`Ctrl+L`) s **výchozím umístěním** a všemi **top-level úkoly začínajícími podtržítkem**; po rozkliknutí *Vybrat ze stromu* lze zvolit **libovolnou cestu** ve stromu, nahoře s **textovým hledáním**. Zvolený cíl vytvoří úkol jako jeho podúkol.
- ✅ **Vícenásobný výběr** ve stromu, seznamu i v režimu **Bez rušení** (Ctrl+klik, Shift+klik, v kartách i `Ctrl+A` / Shift+šipky) – hromadné operace nad označenými úkoly: **smazat**, **přepnout hotovo**, **vlaječka** (`Ctrl+T`), **priorita** (`Ctrl+↑/↓`) a **přesun v pořadí** (`Ctrl+W/Q` posune celý blok).
- ☑️ **Checkbox stavu** ve stromu i na kartách – jedním kliknutím *hotovo* (přeškrtne se), nebo `Ctrl+Enter`. Při dokončení úkolu, který má **nedokončené podúkoly**, se aplikace **zeptá na potvrzení** (platí i pro změnu stavu v detailu).
- 🏷 **Stavy úkolu**: *Ke zpracování*, *Probíhá*, *Čeká* (na vnější věc), *Blokováno*, *Hotovo* – barevně odlišené.
- ⛔ **Blokující úkol** – při přechodu na *Blokováno* lze (nepovinně) zadat úkol, který tě blokuje: v dialogu je **kombobox naposledy použitých** blokujících a **rozklikávací strom** s hledáním. Po **dokončení blokujícího** úkolu přejdou všechny jím blokované na *Ke zpracování*. Osiřelou vazbu (blokující úkol smazán / přesunut) aplikace uklidí sama. Funguje i pro **vícenásobný výběr** – dialog se zeptá jednou a zvolený blokující úkol přiřadí všem označeným.
- 🚧 **Zablokovat sourozence** (`Ctrl+Shift+B`, menu *Úkol* i kontextové menu) – vybraným úkolem zablokuje **všechny sourozence a celé jejich podstromy**, takže zbyde jen to, na čem právě pracuješ. Vybraný úkol ani jeho vlastní podúkoly se nemění. **Přeskočí hotové** (ty už blokovat nejde) i **už blokované** (existující vazba zůstane). Před provedením se zeptá a ukáže seznam; vrátit lze přes `Ctrl+Z`. Po **dokončení** vybraného úkolu se všechno zablokované rozjede zpět na *Ke zpracování*.
- 🤖 **Automatické blokování** – jakmile má úkol aspoň jeden nedokončený **přímý** podúkol a **všechny** jeho nedokončené přímé podúkoly jsou ve stavu *Čeká* nebo *Blokováno*, úkol se sám přepne na *Blokováno* (značka „⛔ auto"). Jakmile podmínka pomine (některý podúkol se rozpracuje/dokončí), vrátí se automaticky na *Ke zpracování*. **Ruční** blokování se nepřepisuje.
- ↩️ **Undo** (`Ctrl+Z`) – vrátí poslední změnu (vytvoření, smazání, přejmenování, přesun, pořadí, vložení, stav, prioritu, vlaječku).
- 📎 **Drag & drop souborů** – přetažením na úkol se přidá jako **odkaz** (soubor se nekopíruje).
- 🔗 **Odkazy mezi úkoly** – cross-reference podle stabilního ID; přežijí přejmenování i přesun.
- 🔀 **Přesun / pořadí přetažením** – drop **na** úkol vnoří, drop **mezi** úkoly mění vlastní pořadí.
- 👁 **Tři režimy zobrazení**: **strom**, **seznam** a **Bez rušení** (karty přes celou šířku okna, výška se přizpůsobí zalomenému názvu; po najetí na kartu se v plovoucím okénku ukáže text úkolu). Pohled skočí na první úkol a odroluje nahoru **jen v Bez rušení, a jen když změna stavu odsune právě aktivní kartu do nižší skupiny** – tehdy by pod kurzorem nic smysluplného nezůstalo. Změna stavu jiné karty, editace názvu, změna metadat ani přidání úkolu pohledem nehýbou; ve stromu a seznamu výběr zůstává na místě vždy. Pozadí karty je **obarvené podle stavu vlevo a priority vpravo** (plynulý přechod, poměr 3:1); úkol s nedokončenými podúkoly nese decentní odznak `↳ N`, úkol s **neprázdným popisem** značku `📝`. Pravým tlačítkem se na kartě otevře **kontextové menu** (mj. *Otevřít v editoru*, kopírovat, přejmenovat, smazat, přepnout hotovo…).
- 🌳 **Stabilní strom** – ručně **sbalené větve zůstanou sbalené** i po změně stavu, přidání úkolu nebo jiné akci (nové úkoly jsou výchozí rozbalené); zachová se i **pozice rolování**, takže pohled neposkočí. Sbalení přežije i přepnutí do seznamu a zpět. Výjimka: úkol vybraný **pod** sbaleným rodičem (např. nově vytvořený podúkol) rodiče rozbalí, aby byl vidět.
- 🧩 **Podúkoly nad rodičem** – v **seznamu i Bez rušení** stojí podúkoly nad svým nadřazeným úkolem; každý rodič si drží souvislý blok, hlouběji vnořené jsou výš.
- 📇 **Skupiny podle stavu v Bez rušení** – karty se řadí do pevného pořadí skupin: **Probíhá + Ke zpracování → Čeká → Blokováno → Hotovo**. Přesun v pořadí (`Ctrl+W/Q`) se pohybuje **jen v rámci skupiny**.
- 📉 **Úsporné zobrazení karet** (`Ctrl+Shift+E`, menu *Zobrazení*, **defaultně zapnuto**) – karty mimo skupinu *Probíhá + Ke zpracování* jsou **nižší** (jen název a cesta, bez řádku vlastností).
- 📐 **Responsivní layout** – úzké/vysoké okno přesune editor pod seznam úkolů.
- 🔢 **Priorita 1–10** (10 = nejvyšší, barevně od zelené po červenou), změna z klávesnice (`Ctrl+↑` / `Ctrl+↓`).
- ↕️ **Vlastní pořadí** – přesun (`Ctrl+W` / `Ctrl+Q`) i tažením; pořadí je `float` (vždy lze vložit mezi). Při přepnutí na „Vlastní pořadí" se převezme aktuální uspořádání.
- 🚩 **Vlaječka** (`_flag`) – rychlé označení, přepínání `Ctrl+T`; lze podle ní i filtrovat.
- 🔎 **Filtrování** – defaultně jen výběr uloženého filtru, **kritéria po rozkliknutí**. Stav/kategorie/tag jsou **multi-select**, priorita **rozmezí od–do**, plus filtr podle vlaječky. Po změně filtru se vybere první vyhovující úkol.
- 💾 **Uložené filtry (presety)** – pamatují podmínky, zobrazení i řazení; lze přiřadit **vlastní zkratku**.
- 📌 **Aktivní úkol zůstává vidět** – nově vytvořený nebo právě upravený úkol, který nevyhovuje filtru, zůstane zobrazený, dokud je aktivní (po opuštění zmizí). Změna filtru naopak přepne na první vyhovující.
- 📊 **Statistiky** (`F8`, menu *Nastavení*) – počty úkolů dle stavu, **založené a uzavřené** za den / týden / posledních 14 dní (sloupcový graf), **doba od posledního uzavřeného úkolu** a **doba do uzavření** úkolu (průměr, medián, min/max + histogram). Čas uzavření se zaznamenává do `_completed` při přechodu na *hotovo*.
- 📅 **Dnešní počty na spodní liště** – průběžně zobrazuje počet **dnes vytvořených** (`+N`) a **dnes dokončených** (`✓N`) úkolů.
- 💾 **Perzistence stavu** – aktivní úkol, filtr a zobrazení se ukládají do `workspace/_state.yaml` a obnoví po startu.
- ⌨️ **Plně ovladatelné klávesnicí** s **konfigurovatelnými zkratkami**.

## Struktura ukládání

```
workspace/
├── _state.yaml             # uložený stav UI (aktivní úkol, filtr, zobrazení)
└── task1/
    ├── task1.md            # tělo úkolu (markdown)
    ├── task1.yaml          # metadata (klíče s podtržítkem)
    └── task2_is_subtask/   # podúkol = podsložka
        ├── task2_is_subtask.md
        └── task2_is_subtask.yaml
```

### Metadata (YAML)

Všechny systémové klíče začínají podtržítkem:

```yaml
_id: 0f4c…              # unikátní ID
_title: Task 1          # zobrazovaný název
_status: todo           # todo | in_progress | waiting | blocked | done
_priority: 5            # 1–10 (10 = nejvyšší)
_category: Práce
_tags: [důležité, projekt]
_created: 2026-06-24T14:00:00
_modified: 2026-06-24T14:05:00
_order: 0               # vlastní pořadí (float, globálně jedinečné)
_flag: false            # vlaječka (Ctrl+T)
_blocked_by: ''         # _id blokujícího úkolu (jen ve stavu blocked)
_auto_blocked: false    # true = blokováno automaticky podle stavu podúkolů
_links:                 # přetažené soubory jako odkazy (necopírují se)
  - name: smlouva.pdf
    path: C:/Users/.../smlouva.pdf
    added: 2026-06-24T14:05:00
_refs:                  # odkazy na jiné úkoly (podle jejich _id)
  - 2b7e…
```

Odkazy mezi úkoly se ukládají jako seznam cizích `_id`. Protože ID je stabilní,
odkaz funguje i po přejmenování nebo přesunu cílového úkolu.

## Instalace a spuštění

```bash
pip install -r requirements.txt
python main.py
```

Na Windows bez konzolového okna: dvojklik na **`run.vbs`** (úplně bez konzole) nebo `run.bat`
(spouští `pythonw`). Aplikace má vlastní moderní ikonu (zaškrtnutý checkbox) v `assets/`
a v hlavním panelu se zobrazuje místo ikony Pythonu.

Při prvním spuštění se vytvoří složka `workspace/` s ukázkovým úkolem.
Jiný pracovní prostor zvolíš přes menu **Soubor → Otevřít prostor…** (`Ctrl+O`).

## Ovládání

Příkazy jsou v **horním menu**, v **kontextovém menu** (pravé tlačítko ve stromu),
přes **klávesové zkratky** a v **příkazové paletě** (`Ctrl+Shift+P`). Žádná lišta tlačítek.

| Akce | Jak |
|------|-----|
| Nový úkol / podúkol | `Ctrl+N` / `Ctrl+Shift+N` (dialog s metadaty) |
| Přejmenovat | `F2` – **inline** přímo v položce stromu |
| Kopírovat / vyjmout / vložit úkol | `Ctrl+C` / `Ctrl+X` / `Ctrl+V` |
| Vložit úkoly z textu | `Ctrl+Shift+V` (dialog: pod / za aktuální / na konec) |
| Přidat soubor jako odkaz | přetáhni soubor z Průzkumníka na úkol (nebo do seznamu odkazů) |
| Odkaz na jiný úkol | panel *Úkoly 🔗* → *Přidat…*; *Přejít* / dvojklik přejde na cíl |
| Přesunout úkol pod jiný | přetáhni úkol **na** cílový úkol (vnoření) |
| Změnit pořadí | přetáhni úkol **mezi** dva úkoly, nebo `Ctrl+W`/`Ctrl+Q` |
| Zobrazení strom/seznam/karty | `Ctrl+L` (cyklit) nebo menu *Zobrazení* |
| Úsporné karty (Bez rušení) | `Ctrl+Shift+E` nebo menu *Zobrazení* (nižší karty mimo Probíhá/Ke zpracování) |
| Filtr | combo uloženého filtru; *Kritéria ▸* rozbalí podmínky |
| Uložit / spravovat filtr | menu *Filtry* (`Ctrl+Shift+S` uložit) |
| Uložit / obnovit | `Ctrl+S` (autosave těla) / `F5` |

## Klávesové ovládání

Aplikace je **plně ovladatelná klávesnicí**. Menu mají mnemoniky (`Alt`+podtržené
písmeno), ve stromu se pohybuješ šipkami, `Enter` skočí z úkolu do editoru.

### Výchozí zkratky (lze změnit)

| Zkratka | Akce | Platí kdy |
|---------|------|-----------|
| `Ctrl+Shift+P` | **Příkazová paleta** | kdekoli |
| `Ctrl+N` / `Ctrl+Shift+N` | Nový úkol / podúkol | kdekoli |
| `F2` | Přejmenovat (inline) | fokus na stromu |
| `Del` | Smazat úkol | fokus na stromu |
| `Ctrl+C` / `Ctrl+X` / `Ctrl+V` | Kopírovat / vyjmout / vložit úkol | fokus na stromu |
| `Ctrl+Shift+V` | Vložit úkoly z textu | fokus na stromu |
| `Ctrl+Z` | Vrátit zpět (undo) | fokus na stromu / kartách |
| `Ctrl+Enter` | Přepnout hotovo | fokus na stromu / kartách |
| `Ctrl+Shift+B` | Zablokovat sourozence (i s podúkoly) | kdekoli |
| `Ctrl+S` / `F5` | Uložit / obnovit | kdekoli |
| `Ctrl+O` | Otevřít prostor | kdekoli |
| `Ctrl+L` | Cyklit zobrazení (strom→seznam→karty) | kdekoli |
| `Ctrl+Shift+D` | Režim Bez rušení (karty) | kdekoli |
| `Ctrl+Shift+E` | Úsporné karty (nižší mimo Probíhá/Ke zpracování) | kdekoli |
| `Ctrl+W` / `Ctrl+Q` | Posunout úkol v pořadí nahoru / dolů | fokus na stromu nebo kartách |
| `Ctrl+↑` / `Ctrl+↓` | Zvýšit / snížit prioritu | fokus na stromu nebo kartách |
| `Ctrl+T` | Přepnout vlaječku 🚩 | kdekoli |
| `Ctrl+,` | Nastavení zkratek | kdekoli |
| `Ctrl+F` | Přejít na hledání/filtr | kdekoli |
| `Ctrl+1` / `Ctrl+2` / `Ctrl+4` | Přejít na strom / editor / odkazy | kdekoli |
| `Ctrl+3` | Přejmenovat úkol (inline) | kdekoli |
| `Ctrl+B` `Ctrl+I` `Ctrl+Shift+X` | Tučné / kurzíva / přeškrtnuté | fokus v editoru |
| `Ctrl+Shift+C` | Inline kód | fokus v editoru |
| `Ctrl+Alt+1`…`3`, `Ctrl+Alt+0` | Nadpis 1–3 / odstavec | fokus v editoru |
| `Ctrl+Shift+8` / `Ctrl+Shift+7` | Odrážkový / číslovaný seznam | fokus v editoru |
| `Ctrl+Shift+Q` / `Ctrl+Shift+H` | Citace / vodorovná čára | fokus v editoru |
| `Ctrl+K` / `Ctrl+E` | Vložit odkaz / přepnout zdroj MD | fokus v editoru |

> Zkratky editoru a stromu jsou **kontextové** – fungují jen když má daný panel
> fokus, aby nekolidovaly s psaním textu.

### Konfigurace zkratek

Menu **Nastavení → Klávesové zkratky…** (`Ctrl+,`) otevře dialog, kde lze každou
zkratku přepsat, vymazat nebo vrátit na výchozí. Změny se ukládají do JSON
souboru v adresáři konfigurace aplikace (`%LOCALAPPDATA%\TaskMaster\Task Master\shortcuts.json`)
a aplikují se okamžitě. Dialog upozorní na kolize ve stejném kontextu.

## Uložené filtry

Menu **Filtry**:

- **Uložit aktuální filtr…** (`Ctrl+Shift+S`) – pojmenuje a uloží aktuální nastavení
  filtrů, zobrazení (strom/seznam) a řazení jako preset.
- **Spravovat uložené filtry…** – dialog, kde u každého presetu nastavíš název,
  zobrazení, řazení a **klávesovou zkratku**, případně podmínky převezmeš z aktuálního filtru.
- Uložené filtry se objeví v menu *Filtry* (a po přiřazení fungují i přes zkratku).

Presety se ukládají do `%LOCALAPPDATA%\TaskMaster\Task Master\filters.json`.

## Výkon

Aplikace drží strom **v paměti**; z disku se čte jen to, co se změnilo:

- **`Workspace.load()`** přebuduje strukturu (cesty se mohou měnit), ale YAML
  parsuje jen u úkolů se změněným otiskem (`mtime`, velikost). Nezměněné uzly
  se recyklují i s odvozenými cache (`_has_body`), takže se nedopočítávají
  z disku. Změna zvenčí (jiný proces, editor) se pozná.
- **Výpis adresářů** jde přes jeden `os.scandir` průchod místo `stat()` na každý
  podadresář – na Windows byl `stat()` většinou času načítání.
- **Karty v Bez rušení** se při přebudování **recyklují**: widget se staví znovu
  jen když se změnil jeho obsah (viz `_card_stamp`). Stavba karty i její layout
  rostou s celkovým počtem úkolů, ne s počtem viditelných.
- Karty se vytvářejí **s rodičem** a plnění běží s vypnutými aktualizacemi –
  jinak Qt novou kartu na okamžik zobrazí jako samostatné okno mimo aplikaci.
- **Pořadí úkolů** (`_order`) je globálně jedinečné už při vzniku. Kolize by
  přinutila `normalize_orders()` přepsat a uložit **všechny** úkoly, což navíc
  zneplatní otisky karet a vynutí jejich kompletní přestavbu.
- **Undo** nekopíruje celý workspace: přejmenování a přesun ukládají jen cesty
  (`moved`), mazání zálohuje jen mazané podstromy (`deleted`), přeuspořádání
  jen metadata (`fields`) a vkládání jen id nových úkolů (`created`). Kopie
  celého prostoru (`snapshot`) zůstává jen jako fallback.

Orientační čísla (medián, 750 úkolů, dřívější hodnoty v závorce): vytvoření
podúkolu ~160 ms (4,1 s), přeuspořádání tažením ~160 ms (3,4 s), vložení ze
schránky ~690 ms (4,0 s), přejmenování / přesun / mazání ~0,7–1 s (~3,5 s),
překreslení stromu ~50 ms, karet ~270 ms, načtení stromu z disku ~670 ms.

## Architektura

```
main.py                 spouštěč QApplication
app/
  constants.py          číselníky stavů, priorit, barvy, možnosti řazení
  storage.py            TaskNode / Workspace – čtení a zápis md+yaml, hierarchie, odkazy
  editor.py             MarkdownEditor – WYSIWYG nad QTextEdit (pojmenované příkazy)
  tasktree.py           TaskTreeWidget – strom/seznam + řazení + drag & drop
  cardview.py           CardView – režim „Bez rušení" (karty + náhled textu)
  filterpanel.py        FilterPanel – sbalený filtr, multi-select, rozmezí priority
  detailpanel.py        TaskDetailPanel – metadata + editor + odkazy
  taskdialog.py         dialog nového úkolu (metadata + zkratky) + volba pozice vkládání
  undo.py               UndoManager – hybridní undo (levné metadatové/created záznamy + snapshot)
  stats.py              Statistiky – výpočet + dialog se sloupcovými grafy (F8)
  commandpalette.py     CommandPalette – příkazová paleta (Ctrl+Shift+P)
  shortcuts.py          ShortcutManager + definice příkazů (zdroj pravdy)
  shortcutdialog.py     dialog pro konfiguraci zkratek
  savedfilters.py       SavedFilter + FilterStore (presety v JSON)
  savedfiltersdialog.py dialog pro správu uložených filtrů
  appicon.py            kreslená moderní ikona aplikace (zaškrtnutý checkbox)
  mainwindow.py         MainWindow – menu, kontextové menu, navigace, propojení
tests/                  headless testy chování stromu a karet (viz níže)
run.vbs / run.bat       spuštění na Windows bez konzolového okna
```

## Testy

```
python tests/run_all.py
```

Testy běží **headless** (Qt offscreen) nad **dočasným workspace** – na `workspace/`
ani na uložené nastavení aplikace nesahají.

> **Pozor při psaní dalších testů:** `MainWindow` si dělá
> `QSettings(ORG_NAME, APP_NAME)` **natvrdo**, takže `QApplication.setOrganizationName()`
> ho neizoluje. Každý test, který vytváří `MainWindow`, musí klíč `workspace`
> v tomto úložišti přesměrovat do dočasného adresáře a původní hodnoty vrátit
> (viz `atexit` v testech) – jinak si okno načte **reálná data uživatele** a
> přepíše v nich metadata.

Testy pokrývají chování, které se snadno
rozbije při úpravách překreslování stromu i karet – **kam se po akci podívá
výběr a pohled**:

| Sada | Co hlídá |
| --- | --- |
| `test_tree_state.py` | sbalené větve a pozice rolování přežijí přebudování, přejmenování i přesun |
| `test_status_focus.py` | změna stavu ve stromu **nepřehodí výběr** na první úkol; v Bez rušení jen při odsunu aktivní karty |
| `test_reparent_rename.py` | drag & drop a `F2` přes `MainWindow` nerozbalí cizí větve |
| `test_cards_scroll.py` | Bez rušení: pohled skáče nahoru **jen** při odsunu aktivní karty |
| `test_block_siblings.py` | blokování sourozenců i s podstromy; výjimky, undo, odblokování |
| `test_cards_recycle.py` | recyklace karet **nezobrazuje zastaralý** obsah |
| `test_load_cache.py` | cache načítání pozná změnu na disku (i zvenčí); chybové cesty |
| `test_stats.py` | statistiky: počty, `_completed`, odolnost vůči poškozeným datům |
| `test_dialogs_filters.py` | dialogy se otevřou; uložené filtry přežijí uložení |
| `test_undo_ops.py` | undo přejmenování, přesunu a mazání bez kopie workspace |
