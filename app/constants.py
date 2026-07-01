"""Konstanty a číselníky pro Task Master."""

import colorsys

# Stavy úkolu (klíč -> popisek)
STATUSES = {
    "todo": "Ke zpracování",
    "in_progress": "Probíhá",
    "blocked": "Blokováno",
    "done": "Hotovo",
}

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
    "blocked": "#ffd6d6",
    "done": "#d4f5d4",
}


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
