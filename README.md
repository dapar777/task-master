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
- ☑️ **Checkbox stavu** ve stromu i na kartách – jedním kliknutím *hotovo* (přeškrtne se), nebo `Ctrl+Enter`. V režimu Bez rušení se **hotové úkoly řadí až za nedokončené**. Při dokončení úkolu, který má **nedokončené podúkoly**, se aplikace **zeptá na potvrzení** (platí i pro změnu stavu v detailu).
- ↩️ **Undo** (`Ctrl+Z`) – vrátí poslední změnu (vytvoření, smazání, přejmenování, přesun, pořadí, vložení, stav, prioritu, vlaječku).
- 📎 **Drag & drop souborů** – přetažením na úkol se přidá jako **odkaz** (soubor se nekopíruje).
- 🔗 **Odkazy mezi úkoly** – cross-reference podle stabilního ID; přežijí přejmenování i přesun.
- 🔀 **Přesun / pořadí přetažením** – drop **na** úkol vnoří, drop **mezi** úkoly mění vlastní pořadí.
- 👁 **Tři režimy zobrazení**: **strom**, **seznam** a **Bez rušení** (karty přes celou šířku okna, výška se přizpůsobí zalomenému názvu; po najetí na kartu se v plovoucím okénku ukáže text úkolu). Po dokončení úkolu skočí výběr na první úkol a odroluje nahoru. Pozadí karty je **obarvené podle stavu vlevo a priority vpravo** (plynulý přechod, poměr 3:1); úkol s nedokončenými podúkoly nese decentní odznak `↳ N`.
- 📐 **Responsivní layout** – úzké/vysoké okno přesune editor pod seznam úkolů.
- 🔢 **Priorita 1–10** (10 = nejvyšší, barevně od zelené po červenou), změna z klávesnice (`Ctrl+↑` / `Ctrl+↓`).
- ↕️ **Vlastní pořadí** – přesun (`Ctrl+W` / `Ctrl+Q`) i tažením; pořadí je `float` (vždy lze vložit mezi). Při přepnutí na „Vlastní pořadí" se převezme aktuální uspořádání.
- 🚩 **Vlaječka** (`_flag`) – rychlé označení, přepínání `Ctrl+T`; lze podle ní i filtrovat.
- 🔎 **Filtrování** – defaultně jen výběr uloženého filtru, **kritéria po rozkliknutí**. Stav/kategorie/tag jsou **multi-select**, priorita **rozmezí od–do**, plus filtr podle vlaječky. Po změně filtru se vybere první vyhovující úkol.
- 💾 **Uložené filtry (presety)** – pamatují podmínky, zobrazení i řazení; lze přiřadit **vlastní zkratku**.
- 📌 **Aktivní úkol zůstává vidět** – nově vytvořený nebo právě upravený úkol, který nevyhovuje filtru, zůstane zobrazený, dokud je aktivní (po opuštění zmizí). Změna filtru naopak přepne na první vyhovující.
- 📊 **Statistiky** (`F8`, menu *Nastavení*) – počty úkolů dle stavu, **založené a uzavřené** za den / týden / posledních 14 dní (sloupcový graf), **doba od posledního uzavřeného úkolu** a **doba do uzavření** úkolu (průměr, medián, min/max + histogram). Čas uzavření se zaznamenává do `_completed` při přechodu na *hotovo*.
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
_status: todo           # todo | in_progress | blocked | done
_priority: 5            # 1–10 (10 = nejvyšší)
_category: Práce
_tags: [důležité, projekt]
_created: 2026-06-24T14:00:00
_modified: 2026-06-24T14:05:00
_order: 0               # vlastní pořadí (float, globálně jedinečné)
_flag: false            # vlaječka (Ctrl+T)
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
| `Ctrl+S` / `F5` | Uložit / obnovit | kdekoli |
| `Ctrl+O` | Otevřít prostor | kdekoli |
| `Ctrl+L` | Cyklit zobrazení (strom→seznam→karty) | kdekoli |
| `Ctrl+Shift+D` | Režim Bez rušení (karty) | kdekoli |
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
run.vbs / run.bat       spuštění na Windows bez konzolového okna
```
