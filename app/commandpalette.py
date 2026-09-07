"""Příkazová paleta (Ctrl+Shift+P) – vyhledávání a spouštění příkazů ve stylu VS Code.

Položka je slovník {label, category, shortcut, run(callable)} nebo – pro
víceúrovňový příkaz – {label, category, children}, kde ``children`` je seznam
položek nebo callable, který ho vrátí (staví se líně, např. seznam podúkolů).
Volba takové položky sestoupí o úroveň: drobečková cesta ukáže „Řadit podle ›
Název", hledání se vyprázdní, Backspace v prázdném poli nebo Esc vrátí zpět.

Hledání je tokenové (každé napsané slovo musí být v „kategorie popisek");
šipky hýbou seznamem, fokus zůstává v poli, Enter spustí. Na kořenové úrovni
se prohledávají i **listy podúrovní** (zploštělé na „Řadit podle › Název ›
Sestupně", hloubka 3), takže „sestupně" najde všechna řazení.

Naposledy použité (VS Code): paleta dostane ``recent`` – seznam cest příkazů
(„Zobrazení|Zoom|150 %", nejnovější první) – a ukáže je na kořeni nahoře,
listy podúrovní zploštělé. Každé spuštění ohlásí cestu přes ``on_run``, aby
si ji volající uložil (klíč = popisky, přejmenování popisku starý záznam tiše zahodí).

Dynamické úrovně: položka se ``search`` (callable(dotaz) -> list[dict]) místo
statických dětí je vyhledávací úroveň – seznam vzniká z napsaného textu
(„Přejít na úkol"). ``extra_search`` daný paletě přidá pár takových zásahů na
kořen, jakmile má dotaz 3+ znaky (úkoly podle názvu).

Prefixy na kořenové úrovni:
    "␣text"  jen příkazy (bez úkolů)
    "u text" jen úkoly (celý strom, i odfiltrované)

``checked=True`` označí aktuální stav (zaškrtnutí), ``icon`` (+ ``icon_color``)
kreslenou ikonu, ``keep_open`` nechá paletu po spuštění otevřenou a přestaví
seznam (přepínání kritérií filtru).

Pravidlo pro aplikaci: každý uživatelský příkaz žije
v MainWindow._build_palette_commands – novou funkci přidej nejdřív tam.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from . import icons, theme

ENTRY_ROLE = Qt.ItemDataRole.UserRole
PATH_SEP = "|"
RECENT_MAX = 8
MODES = {"u": "tasks"}
MODE_LABELS = {"commands": "jen příkazy", "tasks": "jen úkoly"}
MODE_HINT = "␣ jen příkazy   u␣ jen úkoly"
SEARCH_MODES = ("tasks",)   # seznam dodá mode_search


def parse_mode(text: str) -> tuple[str, str]:
    """(režim, dotaz) ze syrového textu pole; režim „all" bez prefixu."""
    if text.startswith(" "):
        return "commands", text.strip()
    for n in (2, 1):
        if len(text) > n and text[n] == " " and text[:n].lower() in MODES:
            return MODES[text[:n].lower()], text[n + 1:].strip()
    return "all", text.strip()


def _children_of(entry: dict) -> list[dict]:
    children = entry.get("children")
    if callable(children):
        children = children()
    return list(children or [])


def _is_branch(entry: dict) -> bool:
    return entry.get("children") is not None or callable(entry.get("search"))


class CommandPalette(QDialog):
    def __init__(self, entries: list[dict], parent=None, title: str = "Příkazy",
                 recent: list[str] | None = None, on_run=None, extra_search=None,
                 mode_search=None) -> None:
        super().__init__(parent)
        for e in entries:
            e.setdefault("_path", [e["label"]])
        self._root = entries
        self._recent = list(recent or [])
        self._on_run = on_run
        self._extra_search = extra_search
        self._mode_search = mode_search
        self._mode = "all"
        self._search_fn = None          # vyhledávací funkce aktuální dynamické úrovně
        self._status_fn = None
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(lambda: self._filter(self.search.text()))
        self._stack: list[tuple[list[dict], str]] = []   # (položky, popisek) nadřazených úrovní
        self._deep: list[dict] | None = None             # zploštělé listy podúrovní (líně)
        self._entries = self._with_recent(entries)
        self._title = title
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(theme.px(640), theme.px(460))

        self.crumb = QLabel()
        self.crumb.setObjectName("pathLabel")
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.list = QListWidget()
        self.list.setUniformItemSizes(True)
        self.list.setIconSize(QSize(theme.px(12), theme.px(12)))
        self.hint = QLabel(f"{MODE_HINT}      ·      ↑↓ pohyb   Enter spustit   Backspace zpět   Esc zavřít")
        self.hint.setObjectName("faintLabel")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignRight)

        layout = QVBoxLayout(self)
        m = theme.px(8)
        layout.setContentsMargins(m, m, m, m)
        layout.setSpacing(theme.px(6))
        layout.addWidget(self.crumb)
        layout.addWidget(self.search)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.hint)

        self.search.textChanged.connect(self._on_text)
        self.list.itemActivated.connect(lambda _: self._run_current())
        self.search.installEventFilter(self)

        self._enter_level(None)
        self.search.setFocus()

    # ------------------------------------------------------------------ úrovně

    def _enter_level(self, entry: dict | None) -> None:
        if entry is not None:
            self._stack.append((self._entries, entry["label"]))
            if callable(entry.get("search")):
                self._search_fn = entry["search"]
                self._status_fn = entry.get("status")
                self._entries = []
            else:
                children = _children_of(entry)
                for c in children:
                    c["_path"] = [*entry["_path"], c["label"]]
                self._entries = children
        self._refresh_level()

    def _go_back(self) -> bool:
        if not self._stack:
            return False
        self._entries, _ = self._stack.pop()
        self._search_fn = None
        self._status_fn = None
        if not self._stack:
            self._entries = self._with_recent(self._root)
        self._refresh_level()
        return True

    def _crumb_text(self) -> str:
        text = "  ›  ".join([self._title, *(label for _, label in self._stack)])
        if not self._stack and self._mode != "all":
            text += f"      [{MODE_LABELS.get(self._mode, self._mode)}]"
        if self._search_fn is not None and callable(self._status_fn):
            try:
                text += f"      {self._status_fn()}"
            except Exception:
                pass
        return text

    def _refresh_level(self) -> None:
        self.crumb.setText(self._crumb_text())
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        if self._search_fn is not None:
            self.search.setPlaceholderText(f"{self._stack[-1][1]}: napiš název…")
        else:
            self.search.setPlaceholderText("Hledat příkaz…" if not self._stack else f"{self._stack[-1][1]} …")
        self._filter("")

    # ------------------------------------------------------------------ naposledy použité

    def _resolve(self, path: list[str]) -> dict | None:
        """Najde list pro cestu popisků (sestupuje přes children)."""
        level = self._root
        entry = None
        for i, label in enumerate(path):
            entry = next((e for e in level if e["label"] == label), None)
            if entry is None or callable(entry.get("search")):
                return None
            if i < len(path) - 1:
                level = _children_of(entry)
                for c in level:
                    c["_path"] = [*entry["_path"], c["label"]]
        return entry if entry is not None and entry.get("children") is None else None

    def _with_recent(self, entries: list[dict]) -> list[dict]:
        """Kořen: naposledy použité příkazy nahoře (nejnovější první), pak zbytek."""
        recent: list[dict] = []
        seen: set[str] = set()
        for key in self._recent[:RECENT_MAX]:
            path = key.split(PATH_SEP)
            leaf = self._resolve(path)
            if leaf is None or key in seen:
                continue
            seen.add(key)
            root = next((e for e in entries if e["label"] == path[0]), leaf)
            recent.append({
                **leaf,
                "label": "  ›  ".join(path),
                "category": root.get("category", ""),
                "children": None,
                "_path": path,
                "_recent": True,
            })
        rest = [e for e in entries if PATH_SEP.join(e["_path"]) not in seen]
        return recent + rest

    # ------------------------------------------------------------------ hluboké hledání

    DEEP_MAX_DEPTH = 3

    def _deep_entries(self) -> list[dict]:
        """Listy všech podúrovní zploštělé („Řadit podle › Název"), aby je dotaz
        na kořeni našel přímo (VS Code ukazuje podpříkazy stejně)."""
        if self._deep is not None:
            return self._deep
        out: list[dict] = []

        def walk(entry: dict, depth: int, category: str) -> None:
            if depth > self.DEEP_MAX_DEPTH:
                return
            for c in _children_of(entry):
                c["_path"] = [*entry["_path"], c["label"]]
                if c.get("children") is not None:
                    walk(c, depth + 1, category)
                elif not callable(c.get("search")):
                    out.append({**c, "label": "  ›  ".join(c["_path"]), "category": category, "_deep": True})

        for root in self._root:
            if root.get("children") is not None:
                walk(root, 1, root.get("category", ""))
        self._deep = out
        return out

    # ------------------------------------------------------------------ seznam

    @staticmethod
    def _matches(e: dict, q: str) -> bool:
        if not q:
            return True
        hay = (e.get("category", "") + " " + e.get("label", "")).lower()
        return all(tok in hay for tok in q.split())

    def _on_text(self, text: str) -> None:
        # hledání v úkolech prochází celý strom – debounce; statické úrovně hned
        mode, q = parse_mode(text) if not self._stack else ("all", text.strip())
        if self._search_fn is not None or mode in SEARCH_MODES or (
                mode == "all" and callable(self._extra_search) and not self._stack and len(q) >= 3):
            self._search_timer.start()
        else:
            self._filter(text)

    def _add_item(self, e: dict, label: str) -> QListWidgetItem:
        it = QListWidgetItem(label)
        if e.get("_recent"):
            it.setIcon(icons.icon("clock", theme.px(12)))
            it.setToolTip("naposledy použité")
        elif e.get("_deep"):
            it.setIcon(icons.icon("subtasks", theme.px(12)))
        elif e.get("icon"):
            it.setIcon(icons.icon(e["icon"], theme.px(12), e.get("icon_color")))
        if e.get("checked") and not e.get("_recent"):
            it.setIcon(icons.icon("check", theme.px(12), theme.current().status_dot["done"]))
        if e.get("tooltip"):
            it.setToolTip(e["tooltip"])
        it.setData(ENTRY_ROLE, e)
        self.list.addItem(it)
        return it

    def _dynamic_items(self, entries: list[dict]) -> None:
        for e in entries:
            e["_dynamic"] = True
            e.setdefault("_path", [e.get("category", ""), e["label"]])
            label = f"{e.get('category', '')}  ·  {e['label']}" if e.get("category") else e["label"]
            sc = e.get("shortcut") or ""
            self._add_item(e, label + (f"      [{sc}]" if sc else ""))

    def _filter(self, q: str) -> None:
        mode, q = parse_mode(q) if not self._stack else ("all", q.strip())
        q = q.lower()
        if mode != self._mode:
            self._mode = mode
            self.crumb.setText(self._crumb_text())
        self.list.clear()
        if not self._stack and mode in SEARCH_MODES:
            entries = []
            if callable(self._mode_search) and q:
                try:
                    entries = self._mode_search(mode, q) or []
                except Exception:
                    entries = []
            self._dynamic_items(entries)
            if self.list.count():
                self.list.setCurrentRow(0)
            return
        if self._search_fn is not None:
            candidates = self._search_fn(q) if len(q) >= 2 else []
            for c in candidates:
                c.setdefault("_path", [*(label for _, label in self._stack), c["label"]])
                c["_dynamic"] = True
        else:
            candidates = list(self._entries)
            if q and not self._stack:
                shown = {PATH_SEP.join(e.get("_path", [e["label"]])) for e in candidates}
                candidates += [d for d in self._deep_entries() if PATH_SEP.join(d["_path"]) not in shown]
        for e in candidates:
            if not e.get("_dynamic") and not self._matches(e, q):
                continue
            label = e["label"]
            if e.get("category"):
                label = f"{e['category']}  ·  {label}"
            if _is_branch(e):
                label += "  ›"
            sc = e.get("shortcut") or ""
            suffix = "      [naposledy použité]" if e.get("_recent") else ""
            if sc:
                suffix = f"      [{sc}]" + ("  · naposledy použité" if e.get("_recent") else "")
            it = self._add_item(e, label + suffix)
            if sc and not e.get("tooltip"):
                it.setToolTip(sc)
        if q and not self._stack and mode == "all" and callable(self._extra_search) and len(q) >= 3:
            try:
                extra = self._extra_search(q)
            except Exception:
                extra = []
            self._dynamic_items(extra)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _run_current(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        entry = item.data(ENTRY_ROLE)
        if _is_branch(entry):
            self._enter_level(entry)
            return
        run = entry.get("run")
        if entry.get("keep_open"):
            # např. přepínání kritérií filtru: spusť a přestav seznam na stejném řádku
            row = self.list.currentRow()
            if callable(run):
                run()
            self._deep = None
            if self._stack:
                # znovu postav aktuální úroveň (děti mohly změnit zaškrtnutí)
                parent_entries, label = self._stack[-1]
                parent = next((e for e in parent_entries if e["label"] == label), None)
                if parent is not None and parent.get("children") is not None:
                    children = _children_of(parent)
                    for c in children:
                        c["_path"] = [*parent["_path"], c["label"]]
                    self._entries = children
            self._filter(self.search.text())
            if self.list.count():
                self.list.setCurrentRow(min(row, self.list.count() - 1))
            return
        self.accept()
        if callable(self._on_run) and not entry.get("_dynamic"):
            try:
                self._on_run(PATH_SEP.join(entry.get("_path", [entry["label"]])))
            except Exception:
                pass
        if callable(run):
            run()

    # ------------------------------------------------------------------ klávesy

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self.search and event.type() == event.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
                row = self.list.currentRow()
                step = 1 if key in (Qt.Key.Key_Down, Qt.Key.Key_PageDown) else -1
                if key in (Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
                    step *= 8
                self.list.setCurrentRow(max(0, min(self.list.count() - 1, row + step)))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._run_current()
                return True
            if key == Qt.Key.Key_Backspace and not self.search.text() and self._go_back():
                return True
            if key == Qt.Key.Key_Escape and self._go_back():
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape and self._go_back():
            return
        super().keyPressEvent(event)

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        par = self.parent()
        if par is not None:
            geo = par.window().frameGeometry()
            self.move(geo.center().x() - self.width() // 2,
                      geo.center().y() - self.height() // 2)
