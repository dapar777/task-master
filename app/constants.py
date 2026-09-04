"""Konstanty a číselníky pro Task Master."""

import colorsys

# Stavy úkolu (klíč -> popisek)
STATUSES = {
    "todo": "Ke zpracování",
    "in_progress": "Probíhá",
    "waiting": "Čeká",
    "snoozed": "Čeká do…",
    "blocked": "Blokováno",
    "done": "Hotovo",
}

# Výchozí odklad, když uživatel ještě žádný nepoužil (dny, hodiny, minuty)
DEFAULT_SNOOZE = (0, 0, 10)
# horní meze posuvníků v dialogu odkladu
SNOOZE_MAX_DAYS = 30


# Priorita 1–10 (10 = nejvyšší). Klíč je celé číslo, popisek text.
PRIORITIES = {i: str(i) for i in range(1, 11)}

DEFAULT_STATUS = "todo"
DEFAULT_PRIORITY = 5

# Migrace ze staré textové priority na číselnou
LEGACY_PRIORITY = {"low": 2, "medium": 5, "high": 8, "critical": 10}

# Barevné odlišení stavů (světlé pozadí pro buňky)
STATUS_COLORS = {
    "todo": "#ffffff",
    "in_progress": "#cfe3ff",
    "waiting": "#ffe9c7",
    "snoozed": "#ffe9c7",       # běžící odklad = čekající (patří k nim i řazením)
    "blocked": "#ffd6d6",
    "done": "#d4f5d4",
}

def status_color(node) -> str:
    """Barva pozadí podle stavu.

    Odklad má barvu čekajícího a po doběhnutí ji SI PONECHÁ – že vypršel,
    dává najevo pozice nahoře a text („Čas vypršel"), ne změna barvy.
    Jediné místo, kde se barva určuje: karty i strom ji berou odsud.
    """
    return STATUS_COLORS.get(node.meta.get("_status", ""), "#ffffff")


def _priority_color(p: int) -> str:
    """1 = zelená (nízká) … 10 = červená (vysoká), pastelové pozadí."""
    frac = (max(1, min(10, p)) - 1) / 9
    hue = 120 * (1 - frac) / 360  # 120° zelená -> 0° červená
    r, g, b = colorsys.hsv_to_rgb(hue, 0.40, 1.0)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


PRIORITY_COLORS = {i: _priority_color(i) for i in range(1, 11)}

# Možnosti řazení (klíč -> popisek)
SORT_OPTIONS = {
    "order": "Vlastní pořadí",
    "title": "Název",
    "priority": "Priorita",
    "status": "Stav",
    "created": "Vytvořeno",
    "modified": "Změněno",
}

# Pořadí pro řazení podle stavu
STATUS_ORDER = list(STATUSES.keys())

# Skupiny stavů pro režim „Bez rušení" (karty). Pořadí skupin je pevné, uvnitř
# skupiny se řadí podle vlastního pořadí. Přesun v pořadí jde jen v rámci skupiny.
# Pozn.: „snoozed" (čeká do…) se do skupin nepočítá staticky – dokud odpočet
# běží, patří mezi „waiting"; jakmile doběhne, jde úplně nahoru (viz
# MainWindow._group_index a ELAPSED_GROUP_INDEX).
STATUS_GROUPS = (
    ("elapsed", ()),          # doběhlé odklady – volají po akci hned
    ("active", ("in_progress", "todo")),
    ("waiting", ("waiting", "snoozed")),
    ("blocked", ("blocked",)),
    ("done", ("done",)),
)

# nadpisy skupin v Bez rušení
GROUP_LABELS = {
    "elapsed": "Čas vypršel",
    "active": "Probíhá + Ke zpracování",
    "waiting": "Čeká",
    "blocked": "Blokováno",
    "done": "Hotovo",
}

# index skupiny pro úkol s doběhlým odkladem (úplně nahoře)
ELAPSED_GROUP_INDEX = 0

# stav -> index skupiny (neznámý stav spadne na konec)
STATUS_GROUP_INDEX = {
    st: i for i, (_key, states) in enumerate(STATUS_GROUPS) for st in states
}

# skupina, která se v úsporném zobrazení NEzmenšuje (plná výška karet)
FULL_HEIGHT_GROUP = "active"

# doběhlý odklad má plnou výšku karty taky – jinak by nejnaléhavější úkoly
# byly nejmenší
FULL_HEIGHT_GROUPS = ("elapsed", "active")

# Klíče metadat v YAML (vše s podtržítkem na začátku = systémová metadata)
META_KEYS = (
    "_id",
    "_title",
    "_status",
    "_priority",
    "_category",
    "_tags",
    "_created",
    "_modified",
    "_links",
)

APP_NAME = "Task Master"
ORG_NAME = "TaskMaster"
