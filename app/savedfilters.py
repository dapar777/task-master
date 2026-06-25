"""Uložené filtry (presety).

Každý uložený filtr drží podmínky filtrování, výchozí zobrazení (strom/seznam),
řazení a volitelnou klávesovou zkratku. Ukládá se do JSON souboru.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class SavedFilter:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Nový filtr"
    # podmínky filtrování (výčty jako seznamy, priorita jako rozmezí)
    name_text: str = ""
    statuses: list = field(default_factory=list)
    priority_min: int = 1
    priority_max: int = 10
    categories: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    flag: object = None  # None = bez filtru, True/False
    # zobrazení a řazení
    view: str = "tree"          # "tree" | "list" | "cards"
    sort_key: str = "title"
    sort_desc: bool = False
    # klávesová zkratka (portable text, např. "Ctrl+Shift+1")
    shortcut: str = ""

    @classmethod
    def from_preset(cls, name: str, preset: dict, view: str, shortcut: str = "") -> "SavedFilter":
        return cls(
            name=name,
            name_text=preset.get("name", ""),
            statuses=list(preset.get("statuses", []) or []),
            priority_min=int(preset.get("priority_min", 1) or 1),
            priority_max=int(preset.get("priority_max", 10) or 10),
            categories=list(preset.get("categories", []) or []),
            tags=list(preset.get("tags", []) or []),
            flag=preset.get("flag", None),
            view=view,
            sort_key=preset.get("sort_key", "title"),
            sort_desc=bool(preset.get("sort_desc", False)),
            shortcut=shortcut,
        )

    def to_preset(self) -> dict:
        """Slovník pro FilterPanel.apply_preset."""
        return {
            "name": self.name_text,
            "statuses": list(self.statuses),
            "priority_min": self.priority_min,
            "priority_max": self.priority_max,
            "categories": list(self.categories),
            "tags": list(self.tags),
            "flag": self.flag,
            "sort_key": self.sort_key,
            "sort_desc": self.sort_desc,
        }


class FilterStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.filters: list[SavedFilter] = []
        self.load()

    def load(self) -> None:
        self.filters = []
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for d in data:
                    known = {k: d[k] for k in SavedFilter().__dict__ if k in d}
                    self.filters.append(SavedFilter(**known))
            except Exception:
                self.filters = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(f) for f in self.filters], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add(self, sf: SavedFilter) -> None:
        self.filters.append(sf)
        self.save()

    def remove(self, filter_id: str) -> None:
        self.filters = [f for f in self.filters if f.id != filter_id]
        self.save()

    def get(self, filter_id: str) -> SavedFilter | None:
        return next((f for f in self.filters if f.id == filter_id), None)
