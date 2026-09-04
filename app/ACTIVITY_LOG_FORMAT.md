# Formát logu aktivního úkolu (`_activity.log`)

Tento dokument popisuje formát souboru, do kterého aplikace zaznamenává
**každou změnu aktivního úkolu** (úkolu, který je právě vybraný ve stromu,
v seznamu nebo v kartách). Log zapisuje modul [`activitylog.py`](activitylog.py)
a čte se pouze lidmi nebo nástroji zvenčí — aplikace samotná ho zpět nenačítá.

## Umístění

```
<workspace_root>/_activity.log
```

Log žije v kořeni workspace (vedle `_state.yaml`), protože se váže ke
konkrétnímu prostoru úkolů a má s ním cestovat (zálohovat se, kopírovat se
apod. spolu s daty). Při otevření jiného workspace se píše do jeho vlastního
`_activity.log`.

## Formát: JSON Lines (`.log`, ale obsah je NDJSON)

Soubor je **append-only**. Jeden řádek = jedna změna aktivního úkolu = jeden
platný JSON objekt. Řádky se od sebe oddělují `\n`. Soubor lze celý načíst
i po řádcích (`for line in f`), nikdy není potřeba parsovat jako jeden celek.

Kódování: UTF-8, bez BOM. Zápis je "append" (`open(path, "a", encoding="utf-8")"`),
takže log roste a nikdy se nepřepisuje ani nemaže sám (rotaci/mazání řeší
uživatel ručně, pokud naroste).

### Tvar jednoho řádku

```json
{"ts": "2026-09-03T14:32:07.123456", "event": "active_task_changed", "path": [{"id": "3f9a...", "title": "Projekt Alfa"}, {"id": "a1b2...", "title": "Sekce Backend"}, {"id": "c9d8...", "title": "Opravit login"}], "breadcrumb": "Projekt Alfa  /  Sekce Backend  /  Opravit login", "task_id": "c9d8...", "title": "Opravit login"}
```

### Pole

| Klíč | Typ | Popis |
|---|---|---|
| `ts` | string | Časové razítko okamžiku změny, lokální čas, ISO 8601 s mikrosekundami (`datetime.now().isoformat()`). Bez časové zóny. |
| `event` | string | Vždy `"active_task_changed"`. Rezervováno pro budoucí rozšíření o jiné typy událostí ve stejném souboru. |
| `path` | array | Celá cesta od kořenového úkolu/projektu až po aktivní úkol, **od kořene k listu**. Každý prvek je objekt `{"id": ..., "title": ...}`. Kořen workspace v poli není (workspace nemá `_id`) — první prvek je vždy top-level úkol/projekt. |
| `path[].id` | string | `_id` (UUID4) daného úkolu v cestě — stejná hodnota jako `TaskNode.task_id` / klíč `_id` v jeho `.yaml`. |
| `path[].title` | string | Název (`title`) daného úkolu v cestě v okamžiku zápisu. Názvy se mohou později změnit — log zachycuje stav v čase zápisu, nedohledává zpětně aktuální název. |
| `breadcrumb` | string | Cesta jako jeden čitelný řetězec, tytéž názvy jako `path[].title`, spojené `"  /  "` (stejný oddělovač a formát, jaký appka používá v UI — viz `breadcrumb()` v `tasktree.py`). Čistě pro pohodlné čtení člověkem, strojově se má parsovat `path`. |
| `task_id` | string | Zkratka — `_id` aktivního (posledního) úkolu z `path`. Usnadňuje filtrování/grep bez nutnosti sahat do pole. |
| `title` | string | Zkratka — `title` aktivního (posledního) úkolu z `path`. |
| `event` `"active_task_cleared"` | — | Zapisuje se, když se aktivní úkol zruší (výběr se zruší, žádný úkol není aktivní). V tomto případě `path` je `[]`, `breadcrumb` je `""` a `task_id`/`title` chybí (klíče nejsou v objektu vůbec přítomny). |

### Kdy se řádek zapisuje

Přesně tehdy, když se změní **identita** aktivního úkolu (jiné `_id` než
předtím), ne při každém překreslení UI. Pokud uživatel opakovaně klikne na
tentýž už aktivní úkol, nic se nezapisuje. Pokud se pouze změní název nebo
jiná metadata aktivního úkolu (ale zůstane vybraný týž úkol), nic se
nezapisuje — to není změna *aktivního úkolu*, ale změna jeho obsahu.

### Příklad souboru (3 řádky)

```
{"ts": "2026-09-03T09:00:01.001000", "event": "active_task_changed", "path": [{"id": "111", "title": "Práce"}], "breadcrumb": "Práce", "task_id": "111", "title": "Práce"}
{"ts": "2026-09-03T09:00:05.500000", "event": "active_task_changed", "path": [{"id": "111", "title": "Práce"}, {"id": "222", "title": "Faktury"}], "breadcrumb": "Práce  /  Faktury", "task_id": "222", "title": "Faktury"}
{"ts": "2026-09-03T09:00:12.250000", "event": "active_task_cleared", "path": [], "breadcrumb": ""}
```

### Jak to číst

**Lidsky:** otevřít v libovolném textovém editoru, řádky jsou krátké a pole
`breadcrumb` samo o sobě stačí na pochopení, co bylo aktivní a kdy (`ts` na
začátku řádku).

**Strojově (Python):**

```python
import json

with open(workspace_root / "_activity.log", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        print(entry["ts"], entry.get("breadcrumb", ""))
```

**Strojově (shell, poslední aktivní úkol):**

```
tail -n 1 _activity.log
```

## Odolnost proti chybám

Zápis jednoho řádku je jednorázový `open(...).write(...)` s okamžitým flush —
pokud aplikace spadne, log obsahuje vše zapsané do pádu a nic víc (žádné
rozbité/nedokončené JSON řádky). Chyba při zápisu logu (např. plný disk,
uzamčený soubor) se **nesmí** projevit pádem aplikace ani ztrátou výběru
úkolu — logger chybu potichu ignoruje (viz `activitylog.py`).
