"""Workspace.load() recykluje nezměněné uzly – nesmí ale zaspat změnu na disku.

Uzel se z paměti přebírá jen když jeho YAML má stejný otisk (mtime, velikost).
Zápis přes aplikaci otisk aktualizuje; zápis „zvenčí" (jiný proces, editor)
musí vést k novému načtení.
"""
import atexit
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.storage import Workspace  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="tm_cache_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


ws = Workspace(tmp)
ws.load()
a = ws.create_root("Alfa")
a.create_child("Alfa sub")
ws.create_root("Beta")
ws.load()

node = lambda t: next(n for n in ws.all_nodes() if n.title == t)  # noqa: E731

print("1) Beze změny na disku se uzly recyklují")
ids_before = {n.title: id(n) for n in ws.all_nodes()}
ws.load()
ids_after = {n.title: id(n) for n in ws.all_nodes()}
check("stejné instance uzlů", ids_before == ids_after)
check("struktura zachována", len(list(ws.all_nodes())) == 3)
check("podúkol má správného rodiče",
      node("Alfa sub").parent is not None
      and node("Alfa sub").parent.title == "Alfa")

print("2) Zápis přes aplikaci se projeví (a uzel se recykluje)")
node("Alfa").set_field("_priority", 9)
ws.load()
check("nová priorita je vidět", node("Alfa").meta.get("_priority") == 9)

print("3) Změna zvenčí (jiný proces) se načte znovu")
target = node("Beta")
yaml_path = target.yaml_path
time.sleep(0.01)  # ať se mtime prokazatelně liší
txt = yaml_path.read_text(encoding="utf-8")
yaml_path.write_text(txt.replace("_priority: 5", "_priority: 1"), encoding="utf-8")
ws.load()
check("změna zvenčí se načetla", node("Beta").meta.get("_priority") == 1)

print("4) Nový úkol na disku se objeví")
ws.create_root("Gama")
ws.load()
check("nový úkol je ve stromu",
      any(n.title == "Gama" for n in ws.all_nodes()))

print("5) Smazaný úkol zmizí")
node("Gama").delete()
ws.load()
check("smazaný úkol je pryč",
      not any(n.title == "Gama" for n in ws.all_nodes()))

print("6) Přejmenování (změna cesty) se projeví")
node("Beta").rename_dir("Beta nova")
ws.load()
check("nový název je ve stromu",
      any(n.title == "Beta nova" for n in ws.all_nodes()))
check("staré jméno je pryč",
      not any(n.title == "Beta" for n in ws.all_nodes()))

print("7) has_body cache přežije load() (kvůli tomu se recykluje)")
n = node("Alfa")
n.write_body("neco")
ws.load()
n = node("Alfa")
check("has_body je True bez čtení z disku", n.has_body is True)
check("cache je předplněná", getattr(n, "_has_body", None) is True)

print("8) Prázdný popis se pozná taky")
node("Alfa").write_body("   ")
ws.load()
check("prázdný popis -> has_body False", node("Alfa").has_body is False)

print("9) Změna zvenčí o STEJNÉ velikosti se taky pozná")
# nejzrádnější případ: otisk je (mtime, velikost) – když se velikost nezmění,
# musí změnu odhalit mtime. Proto se čeká, ať se čas prokazatelně liší.
n = node("Alfa")
n.set_field("_priority", 7)
ws.load()
yp = node("Alfa").yaml_path
size_before = yp.stat().st_size
time.sleep(0.02)
txt = yp.read_text(encoding="utf-8")
yp.write_text(txt.replace("_priority: 7", "_priority: 8"), encoding="utf-8")
check("velikost souboru se nezměnila", yp.stat().st_size == size_before)
ws.load()
check("změna při stejné velikosti se načetla",
      node("Alfa").meta.get("_priority") == 8)

print("10) Recyklovaný uzel nedrží zastaralá metadata")
before_id = id(node("Alfa"))
ws.load()
check("uzel se recykloval", id(node("Alfa")) == before_id)
check("metadata odpovídají disku",
      node("Alfa").meta.get("_priority") == 8)

print("11) Vazby podle _id přežijí recyklaci")
# _id se drží v meta, takže recyklovaný uzel ho musí mít pořád stejné –
# jinak by se rozpadly odkazy mezi úkoly i blokující vazby
src, dst = node("Alfa"), node("Beta nova")
dst_id = dst.task_id
src.add_ref(dst_id)
ws.load()
src = node("Alfa")
check("odkaz na úkol zůstal", dst_id in src.refs)
check("node_by_id odkaz rozřeší",
      ws.node_by_id(dst_id) is not None
      and ws.node_by_id(dst_id).title == "Beta nova")

print("12) Osiřelá blokující vazba se uklidí i po recyklaci")
victim = node("Alfa sub")
victim.set_field("_status", "blocked")
victim.set_blocked_by("neexistujici-id-12345")
ws.load()
fixed = ws.resolve_orphan_blocks()
check("úklid nahlásil opravený úkol",
      any(n.title == "Alfa sub" for n in fixed))
check("úkol je zpět zpracovatelný",
      node("Alfa sub").meta.get("_status") == "todo")

print("13) Chybové cesty: poškozený a prázdný YAML nepoloží načtení")
broken = ws.create_root("Rozbity")
ws.load()
yp = node("Rozbity").yaml_path
yp.write_text("{{{ neplatny: [yaml", encoding="utf-8")
try:
    ws.load()
    check("poškozený YAML nepoložil load()", True)
    check("úkol se načetl s výchozími metadaty",
          node("Rozbity").meta.get("_status") == "todo")
except Exception as e:  # noqa: BLE001
    check(f"poškozený YAML nepoložil load() ({e})", False)
yp.write_text("", encoding="utf-8")
try:
    ws.load()
    check("prázdný YAML nepoložil load()", True)
except Exception as e:  # noqa: BLE001
    check(f"prázdný YAML nepoložil load() ({e})", False)
node("Rozbity").delete()
ws.load()

print("14) Nedostupná položka neskryje zdravé úkoly vedle sebe")
# zamčená složka, vadný symlink nebo výpadek síťové jednotky nesmí vést
# k tomu, že uživateli zmizí i zdravé úkoly ve stejné složce
real_scandir = os.scandir


class _BadEntry:
    name = "nedostupny"
    path = str(tmp / "nedostupny")

    def is_dir(self):
        raise OSError("simulovaná chyba přístupu")


class _FakeIt:
    def __init__(self, good):
        self.items = [_BadEntry()] + list(good)

    def __enter__(self):
        return iter(self.items)

    def __exit__(self, *a):
        return False


def _fake_scandir(p):
    with real_scandir(p) as g:
        good = list(g)
    return _FakeIt(good)


healthy_before = {n.title for n in ws.roots}
os.scandir = _fake_scandir
try:
    ws.load()
    check("zdravé kořeny zůstaly viditelné",
          {n.title for n in ws.roots} == healthy_before)
finally:
    os.scandir = real_scandir
ws.load()
check("po obnovení je stav v pořádku",
      {n.title for n in ws.roots} == healthy_before)

print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
