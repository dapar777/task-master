"""Statistiky (F8): správné počty, odolnost a nezávislost na recyklaci uzlů.

Statistiky agregují přes all_nodes() a čtou _completed z metadat. Recyklace
uzlů při load() proto nesmí výsledky změnit – a poškozená data z ručně
editovaného YAML nesmí dialog položit.
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_stats_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

from app.stats import StatsDialog, compute_stats  # noqa: E402
from app.storage import Workspace  # noqa: E402

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


ws = Workspace(tmp)
ws.load()
for i in range(5):
    ws.create_root(f"Ukol {i}")
ws.load()

node = lambda t: next(n for n in ws.all_nodes() if n.title == t)  # noqa: E731

print("1) Počty podle stavu odpovídají datům")
node("Ukol 1").set_field("_status", "done")
node("Ukol 2").set_field("_status", "done")
node("Ukol 3").set_field("_status", "waiting")
ws.load()
st = compute_stats(list(ws.all_nodes()))
check("2 hotové", st["by_status"].get("done") == 2)
check("1 čekající", st["by_status"].get("waiting") == 1)
check("celkem 5 úkolů", sum(st["by_status"].values()) == 5)

print("2) Dokončení zapíše _completed, odškrtnutí ho zruší")
check("_completed nastaveno", bool(node("Ukol 1").meta.get("_completed")))
node("Ukol 1").set_field("_status", "todo")
ws.load()
check("_completed zrušeno", node("Ukol 1").meta.get("_completed") is None)
check("hotových je teď 1",
      compute_stats(list(ws.all_nodes()))["by_status"].get("done") == 1)

print("3) Recyklace uzlů statistiky nemění")
before = compute_stats(list(ws.all_nodes()))
ws.load()  # recyklace
after = compute_stats(list(ws.all_nodes()))
check("stavy identické", before["by_status"] == after["by_status"])
check("řada vytvořených identická",
      before["created_series"] == after["created_series"])
check("řada dokončených identická",
      before["completed_series"] == after["completed_series"])

print("4) Prázdný workspace nepoloží výpočet ani dialog")
try:
    empty = compute_stats([])
    check("compute_stats([]) prošel", empty is not None)
    d = StatsDialog([], None)
    d.resize(700, 500)
    d.show()
    app.processEvents()
    check("dialog se vykreslil", d.grab().width() > 100)
    d.close()
except Exception as e:  # noqa: BLE001
    check(f"prázdné statistiky bez pádu ({type(e).__name__})", False)

print("5) Poškozená data v metadatech nepoloží statistiky")
# ruční editace YAML může vyrobit nesmyslné datum nebo číslo místo textu
node("Ukol 0").meta["_created"] = "tohle-neni-datum"
node("Ukol 0").save_meta()
node("Ukol 4").meta["_completed"] = 12345
node("Ukol 4").save_meta()
ws.load()
try:
    st = compute_stats(list(ws.all_nodes()))
    check("compute_stats zvládl poškozená data", st is not None)
    check("počet úkolů sedí i tak", sum(st["by_status"].values()) == 5)
    d = StatsDialog(list(ws.all_nodes()), None)
    d.resize(700, 500)
    d.show()
    app.processEvents()
    check("dialog se vykreslil i s poškozenými daty", d.grab().width() > 100)
    d.close()
except Exception as e:  # noqa: BLE001
    check(f"poškozená data bez pádu ({type(e).__name__}: {e})", False)

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
