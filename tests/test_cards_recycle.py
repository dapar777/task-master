"""Recyklace karet v Bez rušení nesmí zobrazovat zastaralý obsah.

CardView při přebudování recykluje widgety, které se nezměnily (viz
_card_stamp). Když se ale obsah změní, karta se MUSÍ přestavět – jinak by
uživatel viděl starý stav, název nebo prioritu.
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

tmp = Path(tempfile.mkdtemp(prefix="tm_recyc_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

from app.cardview import CardView  # noqa: E402
from app.storage import Workspace  # noqa: E402

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


ws = Workspace(tmp)
ws.load()
for i in range(6):
    ws.create_root(f"Ukol {i}")
ws.load()

node = lambda t: next(n for n in ws.all_nodes() if n.title == t)  # noqa: E731

cv = CardView()
cv.resolver = ws.node_by_id
cv.resize(900, 600)
cv.show()


def seq():
    return list(ws.all_nodes())


def texts(key):
    """Veškerý text na kartě (název, cesta, vlastnosti) pro daný klíč."""
    card = cv._cards[key]
    from PySide6.QtWidgets import QLabel
    return " | ".join(lbl.text() for lbl in card.findChildren(QLabel))


cv.populate(seq())
app.processEvents()
k0 = str(node("Ukol 0").path)
k1 = str(node("Ukol 1").path)

print("1) Beze změny se karty recyklují (stejné instance)")
id_before = {k: id(c) for k, c in cv._cards.items()}
cv.populate(seq())
app.processEvents()
id_after = {k: id(c) for k, c in cv._cards.items()}
check("všechny karty recyklované", id_before == id_after)
check("pořadí zachováno", len(cv._order) == len(seq()))

print("2) Změna STAVU kartu přestaví a projeví se v textu")
before_txt = texts(k1)
node("Ukol 1").set_field("_status", "done")
cv.populate(seq())
app.processEvents()
check("karta 'Ukol 1' je nová instance",
      id(cv._cards[k1]) != id_before[k1])
check("ostatní karty se recyklovaly",
      id(cv._cards[k0]) == id_before[k0])
check("text karty se změnil", texts(k1) != before_txt)

print("3) Změna PRIORITY se projeví")
id_mid = id(cv._cards[k0])
txt_mid = texts(k0)
node("Ukol 0").set_field("_priority", 9)
cv.populate(seq())
app.processEvents()
check("karta přestavěna po změně priority", id(cv._cards[k0]) != id_mid)
check("text ukazuje novou prioritu", texts(k0) != txt_mid)

print("4) PŘEJMENOVÁNÍ se projeví v názvu")
n = node("Ukol 2")
n.meta["_title"] = "Ukol 2 prejmenovany"
n.save_meta()
cv.populate(seq())
app.processEvents()
key2 = str(node("Ukol 2 prejmenovany").path)
check("nový název je na kartě", "Ukol 2 prejmenovany" in texts(key2))

print("5) VLAJECKA se projevi")
n = node("Ukol 3")
key3 = str(n.path)
n.set_field("_flag", True)
cv.populate(seq())
app.processEvents()
check("vlajecka je na karte", cv._cards[key3].flagged and cv._cards[key3].flag_label is not None)

print("6) POPIS (znacka) se projevi")
n = node("Ukol 4")
key4 = str(n.path)
n.write_body("nejaky popis")
cv.populate(seq())
app.processEvents()
check("znacka popisu je na karte", cv._cards[key4].has_body)

print("7) Odebraný úkol z karet zmizí")
fewer = [n for n in seq() if n.title != "Ukol 5"]
cv.populate(fewer)
app.processEvents()
check("karta odebraného úkolu je pryč",
      str(node("Ukol 5").path) not in cv._cards)
check("počet karet odpovídá", len(cv._cards) == len(fewer))

print("8) Prázdný seznam nespadne a zobrazí štítek")
cv.populate([])
app.processEvents()
check("žádné karty", not cv._cards)
cv.populate(seq())
app.processEvents()
check("po naplnění jsou karty zpět", len(cv._cards) == len(seq()))

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
cv.close()
sys.exit(1 if fails else 0)
