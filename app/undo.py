"""Undo s několika druhy záznamů, aby běžné operace nebyly drahé.

Kopírování celého workspace (snapshot) je drahé, proto ho používáme jen pro
strukturální operace (smazání, přejmenování, přesun tažením, vložení).
Časté operace mají levné záznamy:

- „fields"  – změna metadat několika uzlů; uloží se jejich předchozí metadata
  a undo je jen zapíše zpět (řazení, stav, priorita, vlaječka).
- „created" – nově vytvořené uzly; undo je prostě smaže.
- „snapshot" – kopie celého workspace (fallback pro složité operace).

Zásobník je jeden, undo je LIFO, takže se druhy záznamů korektně prokládají.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


class UndoManager:
    def __init__(self, limit: int = 50):
        self.limit = limit
        self.entries: list[tuple] = []  # (kind, payload)
        self._base = Path(tempfile.mkdtemp(prefix="tm_undo_"))
        self._counter = 0

    # ----- ukládání záznamů -----
    def snapshot(self, workspace_root: Path) -> None:
        """Kopie celého workspace (drahé – jen pro strukturální operace)."""
        try:
            dest = self._base / f"snap_{self._counter}"
            self._counter += 1
            shutil.copytree(workspace_root, dest)
            self.entries.append(("snapshot", dest))
            self._trim()
        except Exception:
            pass

    def push_fields(self, items) -> None:
        """items: iterovatelné dvojic (node_id, kopie_metadat)."""
        items = [(i, dict(m)) for i, m in items if i]
        if items:
            self.entries.append(("fields", items))
            self._trim()

    def push_created(self, ids) -> None:
        """ids: id nově vytvořených uzlů (undo je smaže)."""
        ids = [i for i in ids if i]
        if ids:
            self.entries.append(("created", ids))
            self._trim()

    def _trim(self) -> None:
        while len(self.entries) > self.limit:
            kind, payload = self.entries.pop(0)
            if kind == "snapshot":
                shutil.rmtree(payload, ignore_errors=True)

    # ----- dotazy -----
    def can_undo(self) -> bool:
        return bool(self.entries)

    # ----- obnova -----
    def restore_last(self, workspace) -> str | None:
        """Vrátí zpět poslední záznam. Vrací druh záznamu, nebo None při chybě.

        Pro „snapshot" volající musí po návratu znovu načíst workspace z disku;
        u „fields"/„created" je paměťový strom už konzistentní.
        """
        if not self.entries:
            return None
        kind, payload = self.entries.pop()
        try:
            if kind == "snapshot":
                self._restore_snapshot(Path(workspace.root), payload)
            elif kind == "fields":
                for nid, meta in payload:
                    node = workspace.node_by_id(nid)
                    if node is not None:
                        node.meta = dict(meta)
                        node.save_meta()
            elif kind == "created":
                for nid in payload:
                    node = workspace.node_by_id(nid)
                    if node is None:
                        continue
                    node.delete()  # rmtree + odebrání z parent.children
                    if node in workspace.roots:  # kořenový uzel
                        workspace.roots.remove(node)
            return kind
        except Exception:
            return None
        finally:
            if kind == "snapshot":
                shutil.rmtree(payload, ignore_errors=True)

    def _restore_snapshot(self, root: Path, snap: Path) -> None:
        for child in list(root.iterdir()):
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        for child in Path(snap).iterdir():
            dest = root / child.name
            if child.is_dir():
                shutil.copytree(child, dest)
            else:
                shutil.copy2(child, dest)

    # ----- úklid -----
    def clear(self) -> None:
        for kind, payload in self.entries:
            if kind == "snapshot":
                shutil.rmtree(payload, ignore_errors=True)
        self.entries = []

    def cleanup(self) -> None:
        shutil.rmtree(self._base, ignore_errors=True)
