# Task Master

Desktopový **hierarchický task manager** pro Windows (Python + PySide6) s **WYSIWYG markdown editorem**.

## Funkce

- 🌳 **Hierarchické úkoly** – podúkoly se ukládají jako podsložky.
- ☑️ **Checkbox stavu** – jedním kliknutím ve stromu označíš úkol jako *hotovo* (přeškrtne se a synchronizuje se stavovým výběrem v detailu).
- 📝 **WYSIWYG markdown editor** – tučné, kurzíva, nadpisy, seznamy, citace, kód, odkazy; přepínání na zdrojový markdown.
- 🗂 **Ukládání na disk** ve formátu složek (viz níže), metadata v YAML.
- 📎 **Drag & drop souborů** – přetažením souboru na úkol se přidá jako **odkaz** na souborový systém (soubor se nekopíruje).
- 🔗 **Odkazy mezi úkoly** – propojení úkolů navzájem (cross-reference) podle stabilního ID; přežijí přejmenování i přesun, kliknutím přejdeš na cílový úkol.
- 🔀 **Přesun úkolů** – přetažením úkolu na jiný (ve stromovém režimu) se změní jeho zařazení.
- 👁 **Tři režimy zobrazení**: **strom**, **seznam** a **Bez rušení** (velké karty přes celou šířku; po najetí na pravou část karty se v plovoucím okénku ukáže text úkolu).
- 🔢 **Priorita 1–10** (10 = nejvyšší, barevně od zelené po červenou).
- ↕️ **Vlastní pořadí** úkolů – přesun klávesami (`Ctrl+W` / `Ctrl+Q`) i **přetažením mezi položky**; pořadí je `float`, takže lze vždy vložit mezi dva. Při přepnutí na „Vlastní pořadí" se pořadí převezme z aktuálně zobrazeného uspořádání.
- ☑️ **Checkboxy stavu** ve stromu i na kartách (Bez rušení); v kartách jde navigovat šipkami, `Space` přepne hotovo, `Enter` otevře.
- 🔎 **Filtrování** podle názvu, stavu, kategorie, priority a tagu + **řazení**. Výčtové vlastnosti (stav, kategorie, tag) lze **zaškrtnout pro víc hodnot**, priorita se filtruje **rozmezím od–do**. Po změně filtru se automaticky vybere první vyhovující úkol.
- 🚩 **Vlaječka** (`_flag`) – rychlé označení úkolu, přepínání `Ctrl+T`.
- 🔢 Změna **priority z klávesnice** (`Ctrl+↑` / `Ctrl+↓`).
- ➕ **Nový úkol** vzniká na **stejné úrovni vedle aktuálního** (jako jeho sourozenec).
- 💾 **Uložené filtry (presety)** – pojmenovaný filtr si pamatuje podmínky, výchozí zobrazení (strom/seznam) i řazení; lze mu přiřadit **vlastní klávesovou zkratku**.

## Struktura ukládání

```
workspace/
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
Jiný pracovní prostor zvolíš přes **Otevřít prostor…** na liště.

## Ovládání

| Akce | Jak |
|------|-----|
| Nový úkol / podúkol | tlačítka vlevo, lišta nebo zkratka |
| Přejmenovat složku úkolu | lišta → *Přejmenovat složku* nebo `F2` |
| Přidat soubor jako odkaz | přetáhni soubor z Průzkumníka na úkol (nebo do seznamu odkazů) |
| Odkaz na jiný úkol | panel *Související úkoly* → *Přidat…*; *Přejít* / dvojklik přejde na cíl |
| Přesunout úkol pod jiný | přetáhni úkol **na** cílový úkol (vnoření) |
| Změnit pořadí | přetáhni úkol **mezi** dva úkoly, nebo `Ctrl+W`/`Ctrl+Q` |
| Strom / seznam | přepínač na liště nebo `Ctrl+L` |
| Řazení | pole *Řadit dle* / *Směr* v panelu filtrů |
| Uložit aktuální filtr | menu *Filtry → Uložit aktuální filtr…* nebo `Ctrl+Shift+S` |
| Spravovat uložené filtry | menu *Filtry → Spravovat uložené filtry…* |
| Použít uložený filtr | menu *Filtry* nebo přiřazená zkratka |
| Uložit | `Ctrl+S` (tělo se ukládá i automaticky) |
| Obnovit z disku | `F5` |

## Klávesové ovládání

Aplikace je **plně ovladatelná klávesnicí**. Menu mají mnemoniky (`Alt`+podtržené
písmeno), ve stromu se pohybuješ šipkami, `Enter` skočí z úkolu do editoru.

### Výchozí zkratky (lze změnit)

| Zkratka | Akce | Platí kdy |
|---------|------|-----------|
| `Ctrl+N` / `Ctrl+Shift+N` | Nový úkol / podúkol | kdekoli |
| `F2` / `Del` | Přejmenovat / smazat úkol | fokus na stromu |
| `Ctrl+S` / `F5` | Uložit / obnovit | kdekoli |
| `Ctrl+O` | Otevřít prostor | kdekoli |
| `Ctrl+L` | Cyklit zobrazení (strom→seznam→karty) | kdekoli |
| `Ctrl+Shift+D` | Režim Bez rušení (karty) | kdekoli |
| `Ctrl+W` / `Ctrl+Q` | Posunout úkol v pořadí nahoru / dolů | fokus na stromu nebo kartách |
| `Ctrl+↑` / `Ctrl+↓` | Zvýšit / snížit prioritu | fokus na stromu nebo kartách |
| `Ctrl+T` | Přepnout vlaječku 🚩 | kdekoli |
| `Ctrl+,` | Otevřít nastavení zkratek | kdekoli |
| `Ctrl+F` | Přejít na hledání/filtr | kdekoli |
| `Ctrl+1`…`Ctrl+4` | Přejít na strom / editor / název / odkazy | kdekoli |
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
  filterpanel.py        FilterPanel – filtry a řazení
  detailpanel.py        TaskDetailPanel – metadata + editor + odkazy
  shortcuts.py          ShortcutManager + definice příkazů (zdroj pravdy)
  shortcutdialog.py     dialog pro konfiguraci zkratek
  savedfilters.py       SavedFilter + FilterStore (presety v JSON)
  savedfiltersdialog.py dialog pro správu uložených filtrů
  appicon.py            kreslená moderní ikona aplikace (zaškrtnutý checkbox)
  mainwindow.py         MainWindow – menu, lišta, navigace, propojení všeho
run.vbs / run.bat       spuštění na Windows bez konzolového okna
```
