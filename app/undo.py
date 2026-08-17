"""Undo s několika druhy záznamů, aby běžné operace nebyly drahé.

Kopírování celého workspace (snapshot) je drahé, proto ho používáme jen pro
strukturální operace (smazání, přejmenování, přesun tažením, vložení).
Časté operace mají levné záznamy:

- „fields"  – změna metadat několika uzlů; uloží se jejich předchozí metadata
  a undo je jen zapíše zpět (řazení, stav, priorita, vlaječka).
- „created" – nově vytvořené uzly; undo je prostě smaže.
- „moved"   – přejmenování a přesun; ukládá jen cesty, obsah se nekopíruje.
- „deleted" – smazané úkoly; zálohuje jen jejich podstromy, ne celý workspace.
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

    def push_deleted(self, paths) -> None:
        """Smazané úkoly: zazálohuje JEN jejich podstromy, ne celý workspace.

        Vrací se přesunem zpět na původní místo. Levnější než snapshot úměrně
        tomu, kolik se maže – u jednoho úkolu z tisíce je rozdíl zásadní.
        """
        saved = []
        for p in paths:
            src = Path(p)
            if not src.exists():
                continue
            dest = self._base / f"del_{self._counter}"
            self._counter += 1
            try:
                shutil.copytree(src, dest)
            except Exception:
                continue
            saved.append((str(src), str(dest)))
        if saved:
            self.entries.append(("deleted", saved))
            self._trim()

    def push_moved(self, old_path, new_path, meta=None) -> None:
        """Přesun/přejmenování adresáře: undo ho vrátí zpět na starou cestu.

        Levná náhrada snapshotu – obsah se nikam nekopíruje, mění se jen cesta.
        `meta` (volitelně) uloží metadata pro obnovu titulku po přejmenování.
        """
        if str(old_path) == str(new_path):
            return
        self.entries.append(
            ("moved", (str(old_path), str(new_path),
                       dict(meta) if meta else None))
        )
        self._trim()

    def _trim(self) -> None:
        while len(self.entries) > self.limit:
            kind, payload = self.entries.pop(0)
            if kind == "snapshot":
                shutil.rmtree(payload, ignore_errors=True)
            elif kind == "deleted":
                for _orig, backup in payload:
                    shutil.rmtree(backup, ignore_errors=True)

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
            elif kind == "moved":
                old_path, new_path, meta = payload
                self._restore_moved(Path(old_path), Path(new_path), meta)
            elif kind == "deleted":
                for orig, backup in payload:
                    src, dst = Path(backup), Path(orig)
                    if not src.exists() or dst.exists():
                        continue
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
            return kind
        except Exception:
            return None
        finally:
            if kind == "snapshot":
                shutil.rmtree(payload, ignore_errors=True)

    @staticmethod
    def _restore_moved(old_path: Path, new_path: Path, meta) -> None:
        """Vrátí adresář z `new_path` zpět na `old_path` (bez kopírování).

        Při přejmenování se mění i názvy .md/.yaml uvnitř (drží se jména
        adresáře), takže se přejmenují zpátky; `meta` obnoví původní titulek.
        """
        if not new_path.exists():
            return
        old_path.parent.mkdir(parents=True, exist_ok=True)
        new_path.rename(old_path)
        old_base, new_base = old_path.name, new_path.name
        if old_base != new_base:
            for ext in (".md", ".yaml"):
                src = old_path / f"{new_base}{ext}"
                if src.exists():
                    src.rename(old_path / f"{old_base}{ext}")
        if meta:
            import yaml  # lokálně: undo jinak na YAML nezávisí
            with open(old_path / f"{old_base}.yaml", "w", encoding="utf-8") as f:
                yaml.safe_dump(meta, f, allow_unicode=True, sort_keys=False,
                               default_flow_style=False)

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
            elif kind == "deleted":
                for _orig, backup in payload:
                    shutil.rmtree(backup, ignore_errors=True)
        self.entries = []

    def cleanup(self) -> None:
        shutil.rmtree(self._base, ignore_errors=True)
