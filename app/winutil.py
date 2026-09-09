"""Drobnosti specifické pro Windows (ctypes). Na jiných platformách jsou to no-op.

Tažení ven z aplikace (úkol ze stromu, text z editoru) běží na Windows přes
OLE ``DoDragDrop``: zdroj je zablokovaný, dokud cíl nevrátí ``Drop()``. Když si
cíl (typicky Total Commander) v ``Drop()`` otevře dotaz „Vložit? Ano/Ne“, Windows
mu bez svolení zdroje nedovolí převzít popředí – dialog je sice vidět, ale
klávesnice (Enter) jde dál do Task Masteru, který na ni během tažení nemůže
reagovat, a celé to „visí“, dokud se dialog neodklikne myší. Zdroj tažení proto
dopředu svolí ``AllowSetForegroundWindow(ASFW_ANY)``; totéž dělá Průzkumník.
"""

from __future__ import annotations

import sys

ASFW_ANY = -1


def allow_foreground_change() -> bool:
    """Dovol libovolnému procesu vzít si popředí (volat při stisku myši, tj.
    před případným začátkem tažení). Vrací, zda Windows svolení přijaly."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.user32.AllowSetForegroundWindow(ASFW_ANY))
    except Exception:
        return False
