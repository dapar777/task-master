"""Vyhodnocení dotazu v hledacím poli: cesta, slova, vzor, diakritika.

Jediné místo pravidel je `app/search.py`; Android má port v
`model/SearchQuery.kt` a testy `SearchQueryTest.kt` – při změně měň obě
strany. Tenhle test běží bez Qt, je to čistá logika.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.search import (  # noqa: E402
    EMPTY, describe, fold, looks_like_regex, parse, push_history, suggest,
)

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


def m(query, title, path=""):
    return parse(query).matches(title, path)


print("1) Prázdný dotaz propustí vše")
check("prázdný text", parse("").empty)
check("jen mezery", parse("   ").empty)
check("samotné lomítko ještě nefiltruje", parse("/").empty)
check("lomítko s mezerou taky ne", parse("/  ").empty)
check("prázdný dotaz vyhoví komukoli", m("", "Cokoli"))

print("2) Hledání v názvu (bez prefixu)")
check("podřetězec sedí", m("nakup", "Nákup mléka"))
check("nesouvisející nesedí", m("auto", "Nákup mléka") is False)
check("nehledá v cestě", m("prace", "Úkol", "Práce  /  Úkol") is False)

print("3) Více slov = všechna musí sedět, na pořadí nezáleží")
check("obě slova v názvu", m("nakup chleba", "Nákup mléka a chleba"))
check("obrácené pořadí", m("chleba nakup", "Nákup mléka a chleba"))
check("chybějící slovo neprojde", m("nakup maso", "Nákup mléka") is False)
check("víc mezer mezi slovy nevadí", m("nakup    chleba", "Nákup a chleba"))
# hledá se podřetězec, ne základ slova: „mleko“ v „mléka“ není (jiný tvar)
check("neohýbá slova", m("mleko", "Nákup mléka") is False)
check("kratší základ slova sedí", m("mlek", "Nákup mléka"))

print("4) Prefix / hledá v celé cestě včetně názvu")
path = "Práce  /  Nákup  /  Jídlo"
check("slovo z prostředka cesty", m("/nakup", "Jídlo", path))
check("slova z různých úrovní (zadání uživatele)", m("/nakup jidlo", "Jídlo", path))
check("slovo z názvu úkolu", m("/jidlo", "Jídlo", path))
check("slovo mimo cestu neprojde", m("/auto", "Jídlo", path) is False)
check("mezera za lomítkem nevadí", m("/ nakup jidlo", "Jídlo", path))
check("bez cesty spadne zpět na název", m("/jidlo", "Jídlo"))

print("5) Bez diakritiky v obou směrech")
check("dotaz bez háčků najde s háčky", m("prilis", "Příliš žluťoučký"))
check("dotaz s háčky najde bez háčků", m("příliš", "Prilis zlutoucky"))
check("velikost písmen nerozhoduje", m("NÁKUP", "nákup mléka"))
check("fold zahodí diakritiku", fold("Příliš Žluťoučký") == "prilis zlutoucky")
check("fold zvládne prázdný text", fold("") == "")
check("diakritika i v cestě", m("/prace jidlo", "Jídlo", "Práce  /  Jídlo"))

print("6) Detekce vzoru je úzká – běžný text vzorem není")
check("verze s tečkou není vzor", not looks_like_regex("verze 1.2"))
check("otazník na konci není vzor", not looks_like_regex("koupit?"))
check("běžná věta není vzor", not looks_like_regex("nakup mleko"))
check("uvozovky nejsou vzor", not looks_like_regex("„nákup“"))
check("kotva na začátku je vzor", looks_like_regex("^Nákup"))
check("kotva na konci je vzor", looks_like_regex("mléko$"))
check("alternativa je vzor", looks_like_regex("(mléko|chléb)"))
check("třída znaků je vzor", looks_like_regex("[0-9]"))
check("kvantifikátor je vzor", looks_like_regex("Nákup.*mléko"))
check("zkratka \\d je vzor", looks_like_regex(r"verze \d"))
check("počet {2} je vzor", looks_like_regex("a{2}"))

print("7) Vzor se opravdu vyhodnotí jako vzor")
check("kotva na začátku sedí", m("^Nakup", "Nákup mléka"))
check("kotva na začátku nesedí uprostřed", m("^mleko", "Nákup mléka") is False)
check("alternativa", m("(mleko|chleba)", "Nákup chleba"))
check("libovolné znaky mezi", m("Nakup.*chleba", "Nákup bílého chleba"))
check("vzor bez diakritiky najde s diakritikou", m("^Nakup.*mleka$", "Nákup mléka"))
check("vzor v cestě", m("/^Prace", "Jídlo", "Práce  /  Jídlo"))
check("tečka jako běžný text (není vzor)", m("verze 1.2", "verze 1.2"))
check("tečka nezastupuje znak, když to není vzor",
      m("verze 1.2", "verze 1x2") is False)

print("8) Rozepsaný nebo chybný vzor nesmí shodit ani vyprázdnit filtr")
# nedokončená závorka detekci nespustí (chybí druhá půlka) -> běžný text
q = parse("(nedokoncena")
check("rozepsaná závorka je běžný text", not q.bad_regex and q.regex is None)
check("a hledá se doslova", q.matches("(nedokoncena zavorka"))
check("nic jiného nenajde", q.matches("úplně jiný úkol") is False)
# tohle uz detekci spustí (třída znaků), ale přeložit to nejde -> fallback na text
bad = parse("[0-9](")
check("chybný vzor je označený", bad.bad_regex)
check("chybný vzor se hledá jako text", bad.matches("verze [0-9]( divná"))
check("chybný vzor nespadne ani nevyprázdní", bad.matches("úplně jiný") is False)

print("9) Popis dotazu pro lištu filtru")
check("prázdný dotaz nemá popis", describe("") == "")
check("název", describe("nakup") == "název ~ „nakup“")
check("cesta", describe("/nakup jidlo") == "cesta ~ „nakup jidlo“")
check("vzor", describe("^Nakup") == "vzor ~ „^Nakup“")
check("vzor v cestě", describe("/^Nakup") == "vzor ~ „^Nakup“")

print("10) Historie hledání")
h = []
h = push_history(h, "nakup")
h = push_history(h, "/prace jidlo")
check("nejnovější je první", h[0] == "/prace jidlo")
check("drží i starší", h == ["/prace jidlo", "nakup"])
h = push_history(h, "nakup")
check("opakovaný dotaz jde navrch, ne dvakrát", h == ["nakup", "/prace jidlo"])
check("duplicita bez ohledu na diakritiku a velikost",
      push_history(["Nákup"], "nakup") == ["nakup"])
check("prázdný dotaz se nepamatuje", push_history(["nakup"], "  ") == ["nakup"])
check("historie má strop", len(push_history(list("abcdefghijklmnopqrstuvwxyz"), "x", limit=5)) == 5)
check("poškozený zápis nespadne", push_history(["ok", None, 5], "novy")[0] == "novy")

print("11) Našeptávání z historie")
hist = ["nakup mleko", "/prace jidlo", "Nákup chleba", "hotovo"]
check("prázdné pole nabídne celou historii", suggest(hist, "") == hist)
check("začátek má přednost před vnitřkem",
      suggest(hist, "nakup") == ["nakup mleko", "Nákup chleba"])
check("bez diakritiky", suggest(hist, "nákup") == ["nakup mleko", "Nákup chleba"])
check("hledá i uvnitř", "/prace jidlo" in suggest(hist, "jidlo"))
check("co je napsané, se nenabízí", "hotovo" not in suggest(hist, "hotovo"))
check("bez shody prázdno", suggest(hist, "xyz") == [])
check("strop návrhů", len(suggest(["a1", "a2", "a3"], "a", limit=2)) == 2)

print("12) EMPTY je sdílená instance a nic nefiltruje")
check("parse prázdného vrací EMPTY", parse("") is EMPTY)
check("EMPTY vyhoví", EMPTY.matches("cokoli", "kdekoli"))

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
