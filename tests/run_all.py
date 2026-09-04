"""Spustí všechny testovací sady a vypíše souhrn.

Testy jsou headless (Qt offscreen) a pracují nad dočasným workspace –
na `workspace/` ani na uložené nastavení aplikace nesahají.

Spuštění:  python tests/run_all.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TESTS = [
    ("test_tree_state.py", "strom: sbalení, rolování, přejmenování, přesun"),
    ("test_status_focus.py", "změna stavu: výběr neskáče na první úkol"),
    ("test_reparent_rename.py", "drag & drop a F2 přes MainWindow"),
    ("test_cards_scroll.py", "Bez rušení: pohled skáče nahoru jen při odsunu aktivní karty"),
    ("test_block_siblings.py", "blokování sourozenců i s jejich podúkoly"),
    ("test_cards_recycle.py", "recyklace karet nezobrazuje zastaralý obsah"),
    ("test_load_cache.py", "cache načítání pozná změnu na disku"),
    ("test_stats.py", "statistiky: počty, odolnost, nezávislost na recyklaci"),
    ("test_dialogs_filters.py", "dialogy a uložené filtry"),
    ("test_undo_ops.py", "undo strukturálních operací bez snapshotu"),
    ("test_status_menu.py", "nastavení stavu z kontextového menu"),
    ("test_sequence.py", "sekvence úkolů: řetěz blokování + dialog"),
    ("test_snooze.py", "odklad: odpočet, obnovení, řazení"),
    ("test_context_key.py", "klávesa kontextového menu ve všech zobrazeních"),
    ("test_order_unique.py", "pořadí nového úkolu je globálně jedinečné (bez přepisu stromu)"),
    ("test_theme.py", "téma: barvy jen v theme.py, karty a strom v obou tématech, přepínač"),
]


def main() -> int:
    here = Path(__file__).resolve().parent
    failed = []
    for name, desc in TESTS:
        print(f"=== {name} – {desc}")
        r = subprocess.run([sys.executable, str(here / name)])
        if r.returncode != 0:
            failed.append(name)
        print()
    if failed:
        print("SELHALO: " + ", ".join(failed))
        return 1
    print(f"Vše prošlo ({len(TESTS)} sady).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
