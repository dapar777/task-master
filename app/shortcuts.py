"""Konfigurovatelné klávesové zkratky.

Definice příkazů (label, kategorie, výchozí zkratka, kontext) jsou jediným
zdrojem pravdy. Uživatelské změny se ukládají do JSON souboru a aplikují na
QAction objekty za běhu.

Kontext určuje, kdy je zkratka aktivní:
    "window" – kdekoli v okně
    "tree"   – jen když má fokus strom úkolů
    "editor" – jen když má fokus editor popisu
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence

# id -> (popisek, kategorie, výchozí zkratka, kontext)
COMMAND_DEFS: dict[str, tuple[str, str, str, str]] = {
    # Navigace / fokus
    "focus.filter": ("Přejít na hledání", "Navigace", "Ctrl+F", "window"),
    "focus.tree": ("Přejít na strom úkolů", "Navigace", "Ctrl+1", "window"),
    "focus.editor": ("Přejít do editoru", "Navigace", "Ctrl+2", "window"),
    "focus.title": ("Přejmenovat úkol (inline)", "Navigace", "Ctrl+3", "window"),
    "focus.links": ("Přejít na odkazy", "Navigace", "Ctrl+4", "window"),
    # Úkoly
    "task.new": ("Nový úkol", "Úkoly", "Ctrl+N", "window"),
    "task.new_sub": ("Nový podúkol", "Úkoly", "Ctrl+Shift+N", "window"),
    "task.rename": ("Přejmenovat složku", "Úkoly", "F2", "tree"),
    "task.delete": ("Smazat úkol", "Úkoly", "Del", "tree"),
    "task.move_up": ("Posunout v pořadí nahoru", "Úkoly", "Ctrl+W", "reorder"),
    "task.move_down": ("Posunout v pořadí dolů", "Úkoly", "Ctrl+Q", "reorder"),
    "task.priority_up": ("Zvýšit prioritu", "Úkoly", "Ctrl+Up", "reorder"),
    "task.priority_down": ("Snížit prioritu", "Úkoly", "Ctrl+Down", "reorder"),
    "task.flag": ("Přepnout vlaječku", "Úkoly", "Ctrl+T", "window"),
    "task.copy": ("Kopírovat úkol", "Úkoly", "Ctrl+C", "tree"),
    "task.cut": ("Vyjmout úkol", "Úkoly", "Ctrl+X", "tree"),
    "task.paste": ("Vložit úkol", "Úkoly", "Ctrl+V", "tree"),
    "task.paste_text": ("Vložit úkoly z textu", "Úkoly", "Ctrl+Shift+V", "tree"),
    "task.toggle_done": ("Přepnout hotovo", "Úkoly", "Ctrl+Return", "reorder"),
    "task.block_siblings": ("Zablokovat sourozence (i s podúkoly)", "Úkoly",
                            "Ctrl+Shift+B", "window"),
    "task.make_sequence": ("Vytvořit sekvenci z označených", "Úkoly",
                           "Ctrl+Shift+R", "window"),
    # Stavy – fungují ve všech zobrazeních (v Bez rušení není combobox detailu).
    # Bez výchozí zkratky, ať nekolidují; jdou přiřadit v Nastavení zkratek.
    "task.status_todo": ("Stav: Ke zpracování", "Úkoly", "", "window"),
    "task.status_in_progress": ("Stav: Probíhá", "Úkoly", "", "window"),
    "task.status_waiting": ("Stav: Čeká", "Úkoly", "", "window"),
    "task.status_snoozed": ("Stav: Čeká do… (odklad)", "Úkoly", "", "window"),
    "task.status_blocked": ("Stav: Blokováno", "Úkoly", "", "window"),
    "edit.undo": ("Vrátit zpět", "Úkoly", "Ctrl+Z", "reorder"),
    # Aplikace / zobrazení
    "app.open_workspace": ("Otevřít prostor…", "Aplikace", "Ctrl+O", "window"),
    "app.save": ("Uložit", "Aplikace", "Ctrl+S", "window"),
    "app.refresh": ("Obnovit z disku", "Aplikace", "F5", "window"),
    "view.cycle": ("Přepnout zobrazení (strom→seznam→karty)", "Zobrazení", "Ctrl+L", "window"),
    "view.tree": ("Zobrazení: strom", "Zobrazení", "", "window"),
    "view.list": ("Zobrazení: seznam", "Zobrazení", "", "window"),
    "view.cards": ("Zobrazení: bez rušení (karty)", "Zobrazení", "Ctrl+Shift+D", "window"),
    "view.compact_cards": ("Úsporné karty (nižší mimo Probíhá/Ke zpracování)", "Zobrazení", "Ctrl+Shift+E", "window"),
    "view.dark_theme": ("Tmavé téma", "Zobrazení", "", "window"),
    "view.zoom_in": ("Přiblížit (zvětšit UI)", "Zobrazení", "Ctrl++", "window"),
    "view.zoom_out": ("Oddálit (zmenšit UI)", "Zobrazení", "Ctrl+-", "window"),
    "view.zoom_reset": ("Původní velikost (100 %)", "Zobrazení", "Ctrl+0", "window"),
    "app.shortcuts": ("Klávesové zkratky…", "Aplikace", "Ctrl+,", "window"),
    "app.command_palette": ("Příkazová paleta…", "Aplikace", "Ctrl+Shift+P", "window"),
    "app.stats": ("Statistiky…", "Aplikace", "F8", "window"),
    # Filtry
    "filter.save": ("Uložit aktuální filtr…", "Filtry", "Ctrl+Shift+S", "window"),
    "filter.manage": ("Spravovat uložené filtry…", "Filtry", "", "window"),
    # Editor (formátování)
    "fmt.bold": ("Tučné", "Editor", "Ctrl+B", "editor"),
    "fmt.italic": ("Kurzíva", "Editor", "Ctrl+I", "editor"),
    "fmt.strike": ("Přeškrtnuté", "Editor", "Ctrl+Shift+X", "editor"),
    "fmt.code": ("Inline kód", "Editor", "Ctrl+Shift+C", "editor"),
    "fmt.h1": ("Nadpis 1", "Editor", "Ctrl+Alt+1", "editor"),
    "fmt.h2": ("Nadpis 2", "Editor", "Ctrl+Alt+2", "editor"),
    "fmt.h3": ("Nadpis 3", "Editor", "Ctrl+Alt+3", "editor"),
    "fmt.paragraph": ("Normální odstavec", "Editor", "Ctrl+Alt+0", "editor"),
    "fmt.bullet": ("Odrážkový seznam", "Editor", "Ctrl+Shift+8", "editor"),
    "fmt.numbered": ("Číslovaný seznam", "Editor", "Ctrl+Shift+7", "editor"),
    "fmt.quote": ("Citace", "Editor", "Ctrl+Shift+Q", "editor"),
    "fmt.hr": ("Vodorovná čára", "Editor", "Ctrl+Shift+H", "editor"),
    "fmt.link": ("Vložit odkaz", "Editor", "Ctrl+K", "editor"),
    "view.toggle_source": ("Editor: zdrojový markdown", "Editor", "Ctrl+E", "editor"),
}

_CONTEXT_MAP = {
    "window": Qt.ShortcutContext.WindowShortcut,
    "tree": Qt.ShortcutContext.WidgetWithChildrenShortcut,
    "editor": Qt.ShortcutContext.WidgetWithChildrenShortcut,
    "reorder": Qt.ShortcutContext.WidgetWithChildrenShortcut,
}


class ShortcutManager:
    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)
        self.overrides: dict[str, str] = {}
        self.actions: dict[str, QAction] = {}
        self._load()

    # ----- konfigurační soubor -----
    def _load(self) -> None:
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.overrides = {
                        k: str(v) for k, v in data.items() if k in COMMAND_DEFS
                    }
            except Exception:
                self.overrides = {}

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(self.overrides, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    # ----- registrace akcí -----
    def register(self, command_id: str, action: QAction) -> None:
        if command_id not in COMMAND_DEFS:
            raise KeyError(f"Neznámý příkaz: {command_id}")
        self.actions[command_id] = action
        _, _, _, context = COMMAND_DEFS[command_id]
        action.setShortcutContext(_CONTEXT_MAP.get(context, Qt.ShortcutContext.WindowShortcut))
        self._apply(command_id)

    def _apply(self, command_id: str) -> None:
        action = self.actions.get(command_id)
        if action is None:
            return
        seq = self.current(command_id)
        action.setShortcut(QKeySequence(seq))
        base_tip = COMMAND_DEFS[command_id][0]
        action.setToolTip(f"{base_tip}  ({seq})" if seq else base_tip)

    # ----- dotazy -----
    def default(self, command_id: str) -> str:
        return COMMAND_DEFS[command_id][2]

    def current(self, command_id: str) -> str:
        return self.overrides.get(command_id, self.default(command_id))

    def label(self, command_id: str) -> str:
        return COMMAND_DEFS[command_id][0]

    def category(self, command_id: str) -> str:
        return COMMAND_DEFS[command_id][1]

    def context(self, command_id: str) -> str:
        return COMMAND_DEFS[command_id][3]

    # ----- změny -----
    def set_shortcut(self, command_id: str, seq: str) -> None:
        seq = seq.strip()
        if seq == self.default(command_id):
            self.overrides.pop(command_id, None)
        else:
            self.overrides[command_id] = seq
        self._apply(command_id)

    def reset(self, command_id: str) -> None:
        self.overrides.pop(command_id, None)
        self._apply(command_id)

    def reset_all(self) -> None:
        self.overrides.clear()
        for cid in list(self.actions):
            self._apply(cid)

    def conflicts(self) -> dict[str, list[str]]:
        """Vrátí seznam příkazů sdílejících stejnou zkratku ve stejném kontextu."""
        seen: dict[tuple[str, str], list[str]] = {}
        for cid in COMMAND_DEFS:
            seq = self.current(cid)
            if not seq:
                continue
            key = (self.context(cid), seq)
            seen.setdefault(key, []).append(cid)
        return {f"{ctx}|{seq}": ids for (ctx, seq), ids in seen.items() if len(ids) > 1}

    def all_command_ids(self) -> list[str]:
        return list(COMMAND_DEFS.keys())
