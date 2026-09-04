"""Log aktivního úkolu – zápis při každé změně vybraného úkolu.

Formát řádků je popsán v ACTIVITY_LOG_FORMAT.md. Log je append-only JSON
Lines soubor `_activity.log` v kořeni workspace.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class ActivityLogger:
    def __init__(self, workspace_root: Path):
        self.path = Path(workspace_root) / "_activity.log"

    def log_active_task(self, node) -> None:
        """Zapíše aktuální úkol (nebo jeho zrušení, pokud node is None)."""
        if node is None:
            entry = {
                "ts": datetime.now().isoformat(),
                "event": "active_task_cleared",
                "path": [],
                "breadcrumb": "",
            }
        else:
            chain = []
            n = node
            while n is not None:
                chain.append(n)
                n = n.parent
            chain.reverse()
            path = [{"id": n.task_id, "title": n.title} for n in chain]
            entry = {
                "ts": datetime.now().isoformat(),
                "event": "active_task_changed",
                "path": path,
                "breadcrumb": "  /  ".join(n.title for n in chain),
                "task_id": node.task_id,
                "title": node.title,
            }
        self._append(entry)

    def _append(self, entry: dict) -> None:
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass
