"""Podtržítkové zkratky (mnemoniky, `&`) pro položky menu.

Popisky příkazů v `shortcuts.COMMAND_DEFS` zůstávají **bez** `&` – paleta,
editor zkratek i stavový řádek je ukazují čisté. `&` se doplňuje až do textu
`QAction` pro menu (`MainWindow._assign_mnemonics`). Protože hlavní menu
i kontextová menu sdílejí tytéž `QAction`, přiděluje `assign()` každému
popisku **jedno** písmeno, které se neopakuje v žádné skupině (= menu), kde
se popisek objeví. Kdo čte text akce zpět (paleta, testy), použije `strip()`.

Pořadí kandidátů: začátky slov bez diakritiky, ostatní písmena bez diakritiky,
teprve pak písmena s diakritikou (stejně jako „Ú&kol“ v hlavním menu – Alt+K
je jistější než Alt+Ú). Popisek, který už `&` má, si ho nechá; doslovný `&`
v textu (názvy uložených filtrů) se zapisuje jako `&&` (`escape()`).
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_MNEMONIC_RE = re.compile(r"(?<!&)&(?!&)")


def escape(text: str) -> str:
    """Doslovný text do menu: každý `&` zdvojit, ať se nestane mnemonikou."""
    return (text or "").replace("&", "&&")


def strip(text: str) -> str:
    """Text bez mnemoniky: jednoduchý `&` zmizí, `&&` je doslovný `&`."""
    return _MNEMONIC_RE.sub("", text or "").replace("&&", "&")


def has_mnemonic(text: str) -> bool:
    return bool(_MNEMONIC_RE.search(text or ""))


def mnemonic_char(text: str) -> str:
    """Písmeno mnemoniky (malé) nebo prázdný řetězec."""
    m = _MNEMONIC_RE.search(text or "")
    if not m or m.end() >= len(text):
        return ""
    return text[m.end()].lower()


def _candidates(label: str) -> list[str]:
    """Písmena v pořadí, v jakém se zkoušejí (viz docstring modulu)."""
    words = _WORD_RE.findall(label)
    initials = [w[0] for w in words if w[0].isalpha()]
    others = [ch for ch in label if ch.isalpha()]
    ordered: list[str] = []
    seen: set[str] = set()
    for tier in (
        [c for c in initials if c.isascii()],
        [c for c in others if c.isascii()],
        [c for c in initials if not c.isascii()],
        [c for c in others if not c.isascii()],
    ):
        for ch in tier:
            if ch.lower() not in seen:
                seen.add(ch.lower())
                ordered.append(ch)
    return ordered


def insert(label: str, ch: str) -> str:
    """Vloží `&` před `ch` – přednostně na začátek slova, jinak první výskyt."""
    for m in _WORD_RE.finditer(label):
        if m.group(0)[0] == ch:
            return label[:m.start()] + "&" + label[m.start():]
    i = label.find(ch)
    if i < 0:
        return label
    return label[:i] + "&" + label[i:]


def assign(groups: list[list[str]]) -> dict[str, str]:
    """Pro popisky ve skupinách (skupina = jedno menu) vrátí {popisek: popisek s &}.

    Popisek ve více skupinách dostane jedno písmeno, které nekoliduje v žádné
    z nich (ostatní skupiny ho pak mají obsazené). Když žádné volné písmeno
    nezbyde, popisek zůstane bez mnemoniky. Vstupní popisky jsou bez `&`
    (doslovný `&` jako `&&`); popisek s hotovou mnemonikou si ji nechá.
    """
    membership: dict[str, list[int]] = {}
    order: list[str] = []
    for gi, labels in enumerate(groups):
        for lbl in labels:
            if lbl not in membership:
                membership[lbl] = []
                order.append(lbl)
            if gi not in membership[lbl]:
                membership[lbl].append(gi)
    used: list[set[str]] = [set() for _ in groups]
    result: dict[str, str] = {}
    for lbl in order:
        if has_mnemonic(lbl):
            ch = mnemonic_char(lbl)
            for gi in membership[lbl]:
                used[gi].add(ch)
            result[lbl] = lbl
    for lbl in order:
        if lbl in result:
            continue
        for ch in _candidates(lbl):
            key = ch.lower()
            if all(key not in used[gi] for gi in membership[lbl]):
                for gi in membership[lbl]:
                    used[gi].add(key)
                result[lbl] = insert(lbl, ch)
                break
        else:
            result[lbl] = lbl
    return result
