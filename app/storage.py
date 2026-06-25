"""Vrstva pro ukládání úkolů na disk.

Struktura na disku::

    <workspace>/
        task1/
            task1.md      # tělo úkolu (markdown)
            task1.yaml     # metadata (klíče s podtržítkem na začátku)
            task2_is_subtask/
                task2_is_subtask.md
                task2_is_subtask.yaml

Adresář = úkol. Soubory .md/.yaml mají vždy stejný základ jako adresář.
Podadresáře jsou podúkoly (rekurzivně).
"""

from __future__ import annotations

import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

import yaml

from .constants import DEFAULT_PRIORITY, DEFAULT_STATUS, LEGACY_PRIORITY

# Znaky nepovolené v názvech adresářů na Windows
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def slugify(title: str) -> str:
    """Z titulku vyrobí bezpečný název adresáře."""
    s = (title or "").strip()
    s = _INVALID.sub("", s)
    s = re.sub(r"\s+", "_", s)
    s = s.strip("._ ")
    return s or "task"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def default_meta(title: str) -> dict:
    ts = now_iso()
    return {
        "_id": str(uuid.uuid4()),
        "_title": title,
        "_status": DEFAULT_STATUS,
        "_priority": DEFAULT_PRIORITY,
        "_category": "",
        "_tags": [],
        "_created": ts,
        "_modified": ts,
        "_order": 0,
        "_flag": False,
        "_links": [],
        "_refs": [],
    }


def unique_dirname(parent: Path, base: str) -> str:
    """Zajistí unikátní název adresáře v rámci rodiče."""
    candidate = base
    i = 2
    while (parent / candidate).exists():
        candidate = f"{base}_{i}"
        i += 1
    return candidate


class TaskNode:
    """Jeden úkol = jeden adresář na disku."""

    def __init__(self, path: Path, parent: "TaskNode | None" = None):
        self.path = Path(path)
        self.parent = parent
        self.children: list[TaskNode] = []
        self.meta: dict = {}
        self._load_meta()

    # ----- cesty -----
    @property
    def name(self) -> str:
        return self.path.name

    @property
    def md_path(self) -> Path:
        return self.path / f"{self.name}.md"

    @property
    def yaml_path(self) -> Path:
        return self.path / f"{self.name}.yaml"

    @property
    def title(self) -> str:
        return self.meta.get("_title") or self.name

    # ----- detekce -----
    @staticmethod
    def is_task_dir(path: Path) -> bool:
        return path.is_dir() and (path / f"{path.name}.yaml").exists()

    # ----- načítání -----
    def _load_meta(self) -> None:
        if self.yaml_path.exists():
            try:
                with open(self.yaml_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                if isinstance(data, dict):
                    self.meta = data
            except Exception:
                self.meta = {}
        # doplnění chybějících klíčů
        base = default_meta(self.name)
        for k, v in base.items():
            self.meta.setdefault(k, v)
        if not self.meta.get("_title"):
            self.meta["_title"] = self.name
        # migrace staré textové priority na číselnou 1–10
        p = self.meta.get("_priority")
        if isinstance(p, str):
            self.meta["_priority"] = LEGACY_PRIORITY.get(p, DEFAULT_PRIORITY)

    def load_children(self) -> None:
        self.children = []
        try:
            entries = sorted(
                [p for p in self.path.iterdir() if TaskNode.is_task_dir(p)],
                key=lambda p: p.name.lower(),
            )
        except OSError:
            entries = []
        for p in entries:
            child = TaskNode(p, parent=self)
            child.load_children()
            self.children.append(child)

    # ----- tělo (markdown) -----
    def read_body(self) -> str:
        if self.md_path.exists():
            try:
                return self.md_path.read_text(encoding="utf-8")
            except Exception:
                return ""
        return ""

    def write_body(self, text: str) -> None:
        self.md_path.write_text(text or "", encoding="utf-8")
        self.touch()

    # ----- metadata -----
    def save_meta(self) -> None:
        with open(self.yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                self.meta,
                f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )

    def touch(self) -> None:
        self.meta["_modified"] = now_iso()
        self.save_meta()

    def set_field(self, key: str, value) -> None:
        self.meta[key] = value
        self.touch()

    def set_order(self, value: float) -> None:
        """Nastaví vlastní pořadí (float) bez změny času úpravy."""
        self.meta["_order"] = float(value)
        self.save_meta()

    @property
    def order(self) -> float:
        try:
            return float(self.meta.get("_order", 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    @property
    def siblings(self) -> list["TaskNode"]:
        return self.parent.children if self.parent else []

    @property
    def flag(self) -> bool:
        return bool(self.meta.get("_flag", False))

    def toggle_flag(self) -> bool:
        new = not self.flag
        self.set_field("_flag", new)
        return new

    # ----- odkazy na soubory (drag & drop) -----
    def add_link(self, file_path: str | Path) -> bool:
        p = Path(file_path)
        target = str(p)
        links = self.meta.setdefault("_links", [])
        if any(l.get("path") == target for l in links):
            return False
        links.append({"name": p.name, "path": target, "added": now_iso()})
        self.touch()
        return True

    def remove_link(self, index: int) -> None:
        links = self.meta.setdefault("_links", [])
        if 0 <= index < len(links):
            links.pop(index)
            self.touch()

    @property
    def links(self) -> list[dict]:
        return self.meta.get("_links", []) or []

    # ----- odkazy na jiné úkoly (cross-reference podle _id) -----
    @property
    def task_id(self) -> str:
        return self.meta.get("_id", "")

    @property
    def refs(self) -> list[str]:
        return self.meta.get("_refs", []) or []

    def add_ref(self, target_id: str) -> bool:
        if not target_id or target_id == self.task_id:
            return False
        refs = self.meta.setdefault("_refs", [])
        if target_id in refs:
            return False
        refs.append(target_id)
        self.touch()
        return True

    def remove_ref(self, target_id: str) -> None:
        refs = self.meta.setdefault("_refs", [])
        if target_id in refs:
            refs.remove(target_id)
            self.touch()

    # ----- hierarchické operace -----
    def create_child(self, title: str) -> "TaskNode":
        base = unique_dirname(self.path, slugify(title))
        child_dir = self.path / base
        return _create_task_dir(child_dir, title, parent=self, append_to=self.children)

    def delete(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)
        if self.parent and self in self.parent.children:
            self.parent.children.remove(self)

    def is_ancestor_of(self, other: "TaskNode") -> bool:
        node = other.parent
        while node is not None:
            if node is self:
                return True
            node = node.parent
        return False

    def move_to(self, new_parent_dir: Path) -> None:
        """Přesune adresář úkolu pod jiný adresář (reparenting)."""
        dest_base = unique_dirname(new_parent_dir, self.name)
        dest = new_parent_dir / dest_base
        shutil.move(str(self.path), str(dest))
        self.path = dest

    def rename_dir(self, new_title: str) -> None:
        """Přejmenuje adresář i soubory podle nového titulku a uloží titulek."""
        new_base = slugify(new_title)
        if new_base != self.name:
            new_base = unique_dirname(self.path.parent, new_base)
            new_path = self.path.parent / new_base
            # nejdřív přejmenovat soubory uvnitř
            old_md = self.md_path
            old_yaml = self.yaml_path
            tmp_md = self.path / f"{new_base}.md"
            tmp_yaml = self.path / f"{new_base}.yaml"
            if old_md.exists():
                old_md.rename(tmp_md)
            if old_yaml.exists():
                old_yaml.rename(tmp_yaml)
            self.path.rename(new_path)
            self.path = new_path
        self.meta["_title"] = new_title
        self.touch()

    # ----- pomocné -----
    def iter_descendants(self):
        for c in self.children:
            yield c
            yield from c.iter_descendants()


def _create_task_dir(task_dir: Path, title: str, parent=None, append_to=None) -> TaskNode:
    task_dir.mkdir(parents=True, exist_ok=False)
    meta = default_meta(title)
    # nový úkol se zařadí na konec vlastního pořadí mezi sourozenci
    if append_to:
        meta["_order"] = float(max((n.order for n in append_to), default=-1.0) + 1.0)
    # tělo zůstává prázdné (bez automatického nadpisu)
    (task_dir / f"{task_dir.name}.md").write_text("", encoding="utf-8")
    with open(task_dir / f"{task_dir.name}.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(meta, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    node = TaskNode(task_dir, parent=parent)
    if append_to is not None:
        append_to.append(node)
    return node


class Workspace:
    """Kořenový pracovní prostor obsahující úkoly nejvyšší úrovně."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.roots: list[TaskNode] = []

    def load(self) -> list[TaskNode]:
        self.roots = []
        for p in sorted(
            [p for p in self.root.iterdir() if TaskNode.is_task_dir(p)],
            key=lambda p: p.name.lower(),
        ):
            node = TaskNode(p)
            node.load_children()
            self.roots.append(node)
        self.normalize_orders()
        return self.roots

    def normalize_orders(self) -> None:
        """Zajistí GLOBÁLNĚ jedinečné pořadí (float) napříč všemi úkoly.

        Pokud se kdekoli pořadí opakuje (např. stará data se samými 0), přečísluje
        všechny úkoly do hloubky tak, aby zůstalo zachováno současné uspořádání
        (v každé skupině podle pořadí, pak názvu). Po jednorázové opravě jsou už
        hodnoty jedinečné a k přepisu nedochází.
        """
        all_nodes = list(self.all_nodes())
        orders = [n.order for n in all_nodes]
        if len(set(orders)) == len(orders):
            return  # už globálně jedinečné

        counter = 0

        def assign(nodes: list[TaskNode]) -> None:
            nonlocal counter
            for n in sorted(nodes, key=lambda n: (n.order, n.title.lower())):
                n.set_order(float(counter))
                counter += 1
                assign(n.children)

        assign(self.roots)

    def next_order(self) -> float:
        """Další globálně jedinečné pořadí (na konec)."""
        return float(max((n.order for n in self.all_nodes()), default=-1.0) + 1.0)

    def create_root(self, title: str) -> TaskNode:
        base = unique_dirname(self.root, slugify(title))
        return _create_task_dir(self.root / base, title, parent=None, append_to=self.roots)

    def move_to_root(self, node: TaskNode) -> None:
        if node.parent and node in node.parent.children:
            node.parent.children.remove(node)
        node.move_to(self.root)
        node.parent = None
        self.roots.append(node)

    # ----- agregace pro filtry -----
    def all_nodes(self):
        for r in self.roots:
            yield r
            yield from r.iter_descendants()

    def node_by_id(self, task_id: str) -> "TaskNode | None":
        if not task_id:
            return None
        for n in self.all_nodes():
            if n.meta.get("_id") == task_id:
                return n
        return None

    # ----- uložený stav UI (do rootu workspace) -----
    @property
    def state_path(self) -> Path:
        return self.root / "_state.yaml"

    def load_state(self) -> dict:
        if self.state_path.exists():
            try:
                data = yaml.safe_load(self.state_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}

    def save_state(self, state: dict) -> None:
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(state, f, allow_unicode=True, sort_keys=False)
        except Exception:
            pass

    def all_categories(self) -> list[str]:
        cats = {n.meta.get("_category", "").strip() for n in self.all_nodes()}
        cats.discard("")
        return sorted(cats, key=str.lower)

    def all_tags(self) -> list[str]:
        tags: set[str] = set()
        for n in self.all_nodes():
            for t in n.meta.get("_tags", []) or []:
                t = str(t).strip()
                if t:
                    tags.add(t)
        return sorted(tags, key=str.lower)
