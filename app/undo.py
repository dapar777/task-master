"""Jednoduché undo přes snapshoty celého workspace (kopie adresáře).

Workspace je malý, takže před každou strukturální operací uložíme kopii a
undo ji obnoví. Spolehlivé i pro operace na souborovém systému.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


class UndoManager:
    def __init__(self, limit: int = 50):
        self.limit = limit
        self.stack: list[Path] = []
        self._base = Path(tempfile.mkdtemp(prefix="tm_undo_"))
        self._counter = 0

    def snapshot(self, workspace_root: Path) -> None:
        try:
            dest = self._base / f"snap_{self._counter}"
            self._counter += 1
            shutil.copytree(workspace_root, dest)
            self.stack.append(dest)
            while len(self.stack) > self.limit:
                old = self.stack.pop(0)
                shutil.rmtree(old, ignore_errors=True)
        except Exception:
            pass

    def can_undo(self) -> bool:
        return bool(self.stack)

    def restore_last(self, workspace_root: Path) -> bool:
        """Obnoví poslední snapshot do workspace. Vrátí True při úspěchu."""
        if not self.stack:
            return False
        snap = self.stack.pop()
        try:
            root = Path(workspace_root)
            for child in list(root.iterdir()):
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
            for child in snap.iterdir():
                dest = root / child.name
                if child.is_dir():
                    shutil.copytree(child, dest)
                else:
                    shutil.copy2(child, dest)
            return True
        except Exception:
            return False
        finally:
            shutil.rmtree(snap, ignore_errors=True)

    def clear(self) -> None:
        for s in self.stack:
            shutil.rmtree(s, ignore_errors=True)
        self.stack = []

    def cleanup(self) -> None:
        shutil.rmtree(self._base, ignore_errors=True)
