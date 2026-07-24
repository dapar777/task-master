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
from datetime import date, datetime
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


def parse_dt(value) -> "datetime | None":
    """Bezpečně převede metadatový čas na datetime.

    Zvládne řetězec (běžný případ – now_iso) i datetime/date objekt, který
    vrátí YAML, když je datum v souboru zapsané bez uvozovek (ruční editace).
    Neplatné/prázdné hodnoty vrací None.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


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
        "_blocked_by": "",
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

    @property
    def has_body(self) -> bool:
        """Má úkol neprázdný popis (po odstranění bílých znaků)?

        Výsledek se cachuje – popis se z disku mění jen přes write_body, který
        cache aktualizuje. Prázdný .md (0 B) odbavíme bez čtení; jinak se soubor
        přečte jednou a ořízne. Bez cache by čtení stovek souborů při každém
        překreslení karet znatelně zpomalovalo.
        """
        cached = getattr(self, "_has_body", None)
        if cached is not None:
            return cached
        try:
            size = self.md_path.stat().st_size
        except OSError:
            self._has_body = False
            return False
        if size == 0:
            self._has_body = False
        elif size > 16:
            # dost velký na to, aby to nebyly jen bílé znaky/odřádkování – nečti
            self._has_body = True
        else:
            self._has_body = bool(self.read_body().strip())
        return self._has_body

    def write_body(self, text: str) -> None:
        self.md_path.write_text(text or "", encoding="utf-8")
        self._has_body = bool((text or "").strip())  # aktualizuj cache
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
        # čas uzavření: zaznamenej při přechodu na „done", zruš při zrušení
        if key == "_status":
            if value == "done":
                self.meta.setdefault("_completed", now_iso())
            else:
                self.meta.pop("_completed", None)
            # vazba na blokující úkol i příznak auto-blokování dávají smysl
            # jen ve stavu „blocked"
            if value != "blocked":
                self.meta["_blocked_by"] = ""
                self.meta.pop("_auto_blocked", None)
        self.meta[key] = value
        self.touch()

    # ----- blokující úkol -----
    @property
    def blocked_by(self) -> str:
        """_id úkolu, který tento úkol blokuje ("" = žádný)."""
        if self.meta.get("_status") != "blocked":
            return ""
        return str(self.meta.get("_blocked_by", "") or "")

    def set_blocked_by(self, target_id: str) -> None:
        self.meta["_blocked_by"] = str(target_id or "")
        self.touch()

    # ----- automatické blokování podle přímých podúkolů -----
    @property
    def auto_blocked(self) -> bool:
        """True, když je task ve stavu blocked kvůli automatickému pravidlu."""
        return (self.meta.get("_status") == "blocked"
                and bool(self.meta.get("_auto_blocked", False)))

    def should_auto_block(self) -> bool:
        """Má se task automaticky zablokovat?

        Ano, právě když má aspoň jeden nedokončený PŘÍMÝ podúkol a všechny jeho
        nedokončené přímé podúkoly jsou ve stavu „čeká" nebo „blokováno".
        """
        pending = [c for c in self.children
                   if c.meta.get("_status") != "done"]
        if not pending:
            return False
        return all(c.meta.get("_status") in ("waiting", "blocked")
                   for c in pending)

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

    def incomplete_subtasks(self) -> int:
        """Počet nedokončených podúkolů (rekurzivně přes celý podstrom)."""
        return sum(1 for d in self.iter_descendants()
                   if d.meta.get("_status") != "done")


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


def serialize_node(node: "TaskNode") -> dict:
    """Zserializuje úkol (vč. podúkolů) pro kopírování – bez id a časů.

    _blocked_by se nepřenáší: kopie by jinak skrytě zdědila blokující vazbu,
    kterou uživatel u ní nezadal (a odkazovala by na cizí úkol).
    """
    skip = {"_id", "_created", "_modified", "_order", "_blocked_by"}
    return {
        "title": node.title,
        "meta": {k: v for k, v in node.meta.items() if k not in skip},
        "body": node.read_body(),
        "children": [serialize_node(c) for c in node.children],
    }


def parse_indented_text(text: str) -> list[dict]:
    """Z odsazeného textu vyrobí stromovou strukturu úkolů.

    Příklad::
        Task1
          Subtask1
        Task2
    """
    out_roots: list[dict] = []
    stack: list[tuple[int, dict]] = []  # (indent, node)
    for raw in (text or "").splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" \t"))
        node = {"title": raw.strip(), "children": []}
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(node)
        else:
            out_roots.append(node)
        stack.append((indent, node))
    return out_roots


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

    def create_subtree(self, parent: "TaskNode | None", data: dict) -> TaskNode:
        """Vytvoří úkol (a rekurzivně podúkoly) z dat (copy/paste, text)."""
        if parent is None:
            node = self.create_root(data.get("title", "Úkol"))
        else:
            node = parent.create_child(data.get("title", "Úkol"))
        meta = data.get("meta")
        if meta:
            for k, v in meta.items():
                node.meta[k] = v
            node.save_meta()
        body = data.get("body")
        if body is not None:
            node.write_body(body)
        for ch in data.get("children", []) or []:
            self.create_subtree(node, ch)
        return node

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

    # ----- blokování -----
    def blocked_by_node(self, node: "TaskNode") -> list["TaskNode"]:
        """Úkoly, které blokuje daný úkol (a čekají na jeho dokončení)."""
        tid = node.task_id
        if not tid:
            return []
        return [n for n in self.all_nodes() if n.blocked_by == tid]

    def resolve_orphan_blocks(self) -> list["TaskNode"]:
        """Odblokuje úkoly, jejichž blokující úkol už neexistuje.

        Blokující úkol mohl zmizet smazáním nebo přesunem (cut/paste mění _id).
        Bez úklidu by takový úkol uvázl ve stavu Blokováno navždy – odblokování
        se totiž spouští jen při dokončení blokujícího, které už nenastane.
        Vrací odblokované úkoly (pro hlášku). Volat po workspace.load().
        """
        ids = {n.task_id for n in self.all_nodes() if n.task_id}
        fixed = []
        for n in self.all_nodes():
            bid = n.blocked_by
            if bid and bid not in ids:
                n.set_field("_status", "todo")  # set_field zruší i _blocked_by
                fixed.append(n)
        return fixed

    def recent_blockers(self, limit: int = 10) -> list[str]:
        """_id naposledy použitých blokujících úkolů (nejnovější první)."""
        hist = self.load_state().get("_recent_blockers", []) or []
        return [str(i) for i in hist][:limit]

    def push_recent_blocker(self, task_id: str, limit: int = 10) -> None:
        """Zapamatuje si blokující úkol pro rychlou nabídku příště."""
        if not task_id:
            return
        state = self.load_state()
        hist = [str(i) for i in (state.get("_recent_blockers", []) or [])]
        if task_id in hist:
            hist.remove(task_id)
        hist.insert(0, task_id)
        state["_recent_blockers"] = hist[:limit]
        self.save_state(state)

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
