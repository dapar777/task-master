# -*- coding: utf-8 -*-
"""Vyhodnocení dotazu v hledacím poli filtru.

Jedno místo, kde se rozhoduje, CO uživatel napsal – používá ho filtr
(`filterpanel.matches`) i příkazová paleta, aby se obě místa chovala stejně.
Android má port v `model/SearchQuery.kt`; při změně pravidel měň obě strany
a drž znění testů.

Tři vrstvy, všechny volitelné a kombinovatelné:

1. **Rozsah** – dotaz začínající ``/`` hledá v celé CESTĚ úkolu (drobečky
   od kořene včetně jeho názvu), jinak jen v názvu. Lomítko je bezpečný
   předěl: `slugify` ho z názvů adresářů odstraňuje, takže v titulcích
   prakticky nebývá.
2. **Slova** – dotaz se dělí mezerami a musí sedět VŠECHNA (AND), v
   libovolném pořadí. Přebírá chování hledání úkolů v paletě.
3. **Regulární výraz** – když dotaz *zjevně* vypadá jako vzor, vyhodnotí se
   jako vzor (celý dotaz, bez dělení na slova). Detekce je schválně úzká:
   samotná tečka nebo otazník v běžném názvu („verze 1.2“, „koupit?“) vzor
   nedělá, jinak by se hledání tiše chovalo jinak, než uživatel čeká.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

#: prefix přepínající hledání z názvu na celou cestu
PATH_PREFIX = "/"


def fold(text: str) -> str:
    """Malá písmena bez diakritiky – „Jídlo“ i „jidlo“ se potkají.

    Rozloží znaky na písmeno + diakritiku (NFD) a diakritiku zahodí, takže
    hledání je nezávislé na háčcích a čárkách v obou směrech. Android má
    ekvivalent v `SearchQuery.fold` (java.text.Normalizer), formát dat se
    tím nemění – skládá se jen porovnávaný text.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))

#: Znaky/konstrukce, které běžný název úkolu prakticky neobsahuje, ale regulární
#: výraz ano. Schválně tu NENÍ samotná ``.`` ani ``?`` (viz docstring modulu).
_REGEX_HINTS = (
    r"\[[^\]]*\]",      # třída znaků: [abc], [0-9]
    r"\([^)]*\|[^)]*\)",  # alternativa v závorkách: (a|b)
    r"\\[dwsbDWSB]",    # zkratky: \d \w \s \b
    r"[.\w\)\]]\{\d+(,\d*)?\}",  # kvantifikátor {2}, {2,}, {2,5}
    r"[.\w\)\]][*+]",   # kvantifikátor * + po znaku (ne na začátku)
    r"^\^",             # kotva na začátku
    r"\$$",             # kotva na konci
)
_REGEX_RE = re.compile("|".join(_REGEX_HINTS))


def looks_like_regex(text: str) -> bool:
    """Vypadá dotaz jako regulární výraz? (úzká detekce, viz modul)"""
    return bool(text) and bool(_REGEX_RE.search(text))


@dataclass(frozen=True)
class SearchQuery:
    """Rozebraný dotaz z hledacího pole."""

    #: hledat v celé cestě místo jen v názvu
    in_path: bool = False
    #: slova, která musí sedět všechna (prázdné u regulárního výrazu)
    words: tuple[str, ...] = ()
    #: přeložený vzor, nebo None
    regex: "re.Pattern[str] | None" = None
    #: dotaz je prázdný (nic nefiltruje)
    empty: bool = True
    #: uživatel napsal vzor, ale nešel přeložit – hledá se jako obyčejný text
    bad_regex: bool = False

    def matches(self, title: str, path: str = "") -> bool:
        """Vyhovuje úkol s daným názvem (a cestou) dotazu?

        Porovnává se bez diakritiky a bez ohledu na velikost písmen
        (viz [fold]) – „jidlo“ najde „Jídlo“ i naopak.
        """
        if self.empty:
            return True
        haystack = fold(path if self.in_path and path else title)
        if self.regex is not None:
            return bool(self.regex.search(haystack))
        return all(w in haystack for w in self.words)


#: prázdný dotaz – propustí vše
EMPTY = SearchQuery()


def parse(text: str) -> SearchQuery:
    """Rozebere text hledacího pole na [SearchQuery]."""
    raw = (text or "").strip()
    if not raw:
        return EMPTY

    in_path = raw.startswith(PATH_PREFIX)
    if in_path:
        raw = raw[len(PATH_PREFIX):].strip()
        if not raw:
            # samotné „/“ ještě není dotaz – uživatel teprve píše
            return EMPTY

    if looks_like_regex(raw):
        try:
            # vzor se skládá stejně jako text, proti kterému se porovnává,
            # aby „^Nákup“ sedlo i na „Nakup“ (a naopak)
            return SearchQuery(in_path=in_path,
                               regex=re.compile(fold(raw), re.IGNORECASE),
                               empty=False)
        except re.error:
            # rozepsaný nebo chybný vzor nesmí filtr shodit ani vyprázdnit
            return SearchQuery(in_path=in_path, words=(fold(raw),),
                               empty=False, bad_regex=True)

    return SearchQuery(in_path=in_path,
                       words=tuple(fold(raw).split()),
                       empty=False)


#: klíč historie hledání v `_state.yaml` (sdílený s Androidem)
HISTORY_KEY = "_search_history"

#: kolik dotazů si prostor pamatuje
HISTORY_LIMIT = 20


def push_history(history, text: str, limit: int = HISTORY_LIMIT) -> list[str]:
    """Nový seznam historie: [text] navrch, bez duplicit, omezená délka.

    Duplicita se pozná bez ohledu na velikost písmen a diakritiku, ale ukládá
    se přesně to, co uživatel napsal. Prázdný dotaz se nepamatuje.
    """
    q = (text or "").strip()
    if not q:
        return [h for h in (history or []) if isinstance(h, str)][:limit]
    key = fold(q)
    out = [q]
    for h in history or []:
        if isinstance(h, str) and h.strip() and fold(h) != key:
            out.append(h)
    return out[:limit]


def suggest(history, text: str, limit: int = 10) -> list[str]:
    """Návrhy z historie pro rozepsaný dotaz.

    Prázdné pole nabídne celou historii (nejnovější první). Jinak se hledá
    bez diakritiky; dotazy začínající zadaným textem jdou před ty, které ho
    mají uprostřed, aby psaní od začátku dávalo očekávané pořadí.
    """
    q = fold((text or "").strip())
    items = [h for h in (history or []) if isinstance(h, str) and h.strip()]
    if not q:
        return items[:limit]
    starts, contains = [], []
    for h in items:
        f = fold(h)
        if f == q:
            continue  # co je právě napsané, není návrh
        if f.startswith(q):
            starts.append(h)
        elif q in f:
            contains.append(h)
    return (starts + contains)[:limit]


def describe(text: str) -> str:
    """Krátký popis dotazu do lišty filtru („cesta ~ …“, „vzor ~ …“)."""
    q = parse(text)
    if q.empty:
        return ""
    body = (text or "").strip()
    if q.in_path:
        body = body[len(PATH_PREFIX):].strip()
    kind = "vzor" if q.regex is not None else ("cesta" if q.in_path else "název")
    return f"{kind} ~ „{body}“"
