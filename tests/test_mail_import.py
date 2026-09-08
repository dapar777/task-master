"""Načítání úkolů z e-mailu: parsování zpráv (předmět, tělo, HTML, přílohy),
založení úkolů do sekce _INBOX (vznik, opětovné použití, duplicity podle
Message-ID, přílohy s relativní cestou), nastavení a průchod přes MainWindow
s falešnou schránkou (označení jako přečtené, aktivní úkol, paleta)."""
import atexit
import os
import shutil
import sys
import tempfile
from email.message import EmailMessage
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp(prefix="tm_mail_"))
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

from app.constants import APP_NAME, ORG_NAME  # noqa: E402

_s = QSettings(ORG_NAME, APP_NAME)
_orig = {k: _s.value(k) for k in ("workspace", "view_mode", "mail_interval_min")}


def _restore_settings():
    s = QSettings(ORG_NAME, APP_NAME)
    for k, v in _orig.items():
        if v is None:
            s.remove(k)
        else:
            s.setValue(k, v)
    s.sync()


atexit.register(_restore_settings)
_s.setValue("workspace", str(tmp / "ws_window"))
_s.setValue("view_mode", "tree")
_s.setValue("mail_interval_min", 0)  # reálné nastavení uživatele nesmí spustit timer
_s.sync()

from app import mailimport  # noqa: E402
from app.mailimport import (  # noqa: E402
    INBOX_TITLE, MAIL_ID_KEY, MailMessage, MailSettings, import_messages, parse_message,
    safe_filename, unique_filename,
)
from app.storage import Workspace  # noqa: E402

fails = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


def raw_mail(subject, body, *, html=None, attachments=(), msg_id="<a@b>", sender="Jan Novák <jan@example.cz>"):
    m = EmailMessage()
    m["Subject"] = subject
    m["From"] = sender
    m["To"] = "dapar777_taskmaster@seznam.cz"
    m["Date"] = "Mon, 08 Sep 2026 12:05:00 +0200"
    if msg_id:
        m["Message-ID"] = msg_id
    if html is not None and body is None:
        m.set_content(html, subtype="html")
    else:
        m.set_content(body or "")
        if html is not None:
            m.add_alternative(html, subtype="html")
    for name, data, maintype, subtype in attachments:
        m.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return m.as_bytes()


# --- 1) parsování zpráv ---
print("1) parse_message")
msg = parse_message("7", raw_mail("Žluťoučký kůň: zavolat", "Ahoj,\r\nzavolej prosím.\r\n"))
check("předmět s diakritikou (RFC 2047)", msg.subject == "Žluťoučký kůň: zavolat")
check("uid, Message-ID, odesílatel", msg.uid == "7" and msg.message_id == "<a@b>" and "jan@example.cz" in msg.sender)
check("datum v lokálním čase (formát)", len(msg.date) == 16 and msg.date.startswith("2026-09-08"))
check("tělo bez CRLF a okrajů", msg.text == "Ahoj,\nzavolej prosím.")
check("bez příloh", msg.attachments == [])

msg = parse_message("8", raw_mail(None, None, html="<p>Nakoupit <b>mléko</b></p><ul><li>chléb</li></ul>", msg_id=""))
check("chybějící předmět -> „(bez předmětu)“", msg.subject == "(bez předmětu)")
check("HTML tělo -> markdown", "**mléko**" in msg.text and "- chléb" in msg.text)
check("bez Message-ID je message_id prázdné", msg.message_id == "")

pdf = b"%PDF-1.4 fake"
msg = parse_message("9", raw_mail("S přílohou", "viz příloha", html="<p>viz <i>příloha</i></p>",
                                  attachments=[("faktura.pdf", pdf, "application", "pdf"),
                                               ("poznámky.txt", b"text", "text", "plain")]))
check("text/plain má přednost před HTML", msg.text == "viz příloha")
check("přílohy: název + obsah", [a[0] for a in msg.attachments] == ["faktura.pdf", "poznámky.txt"]
      and msg.attachments[0][1] == pdf and msg.attachments[1][1].strip() == b"text")

from app.htmlmd import html_to_markdown  # noqa: E402
md = html_to_markdown('<html><head><style>p{}</style></head><body><h2>Plán</h2><p>Viz <a href="https://x.cz/a">web</a> a '
                      '<em> kurzíva </em>.</p><ol><li>první<ul><li>vnořený</li></ul></li><li>druhý</li></ol>'
                      '<blockquote>citace</blockquote><pre>a &lt; b\n  c</pre><table><tr><td>A</td><td>B</td></tr></table></body></html>')
check("html: nadpis, odkaz, kurzíva s mezerami",
      md.startswith("## Plán\n\nViz [web](https://x.cz/a) a *kurzíva*.") and "<style>" not in md and "p{}" not in md)
check("html: číslovaný + vnořený seznam", "1. první\n  - vnořený\n2. druhý" in md)
check("html: citace, kód, tabulka", "> citace" in md and "```\na < b\n  c\n```" in md and "A | B" in md)
check("safe_filename: cesta a zakázané znaky", safe_filename(r"C:\x\fa:kt*ura?.pdf") == "faktura.pdf")
check("safe_filename: prázdný -> priloha", safe_filename("  . ") == "priloha")
(tmp / "u").mkdir()
(tmp / "u" / "a.pdf").write_bytes(b"1")
(tmp / "u" / "a_2.pdf").write_bytes(b"1")
check("unique_filename čísluje", unique_filename(tmp / "u", "a.pdf") == "a_3.pdf"
      and unique_filename(tmp / "u", "b.pdf") == "b.pdf")

# --- 2) založení úkolů ve workspace ---
print("2) import_messages")
ws = Workspace(tmp / "ws")
ws.load()
ws.create_root("Projekt")
m1 = MailMessage("1", "<m1@x>", "Zaplatit fakturu", "Účtárna <uc@x.cz>", "2026-09-08 10:00", "Do pátku.",
                 [("faktura.pdf", pdf), ("faktura.pdf", "druhá".encode("utf-8"))])
m2 = MailMessage("2", "<m2@x>", "Bez těla", "", "", "", [])
res = import_messages(ws, [m1, m2])
inbox = res.inbox
check("sekce _INBOX vznikla jako kořen", inbox is not None and inbox.parent is None and inbox.title == INBOX_TITLE)
check("úkoly jsou pod _INBOX", [c.title for c in inbox.children] == ["Zaplatit fakturu", "Bez těla"])
t1 = inbox.children[0]
check("Message-ID v metadatech", t1.meta.get(MAIL_ID_KEY) == "<m1@x>")
check("popis: odesílatel, datum, text", "**Od:** Účtárna" in t1.read_body() and "**Datum:** 2026-09-08 10:00" in t1.read_body()
      and t1.read_body().rstrip().endswith("Do pátku."))
check("přílohy na disku v adresáři úkolu", (t1.path / "faktura.pdf").read_bytes() == pdf
      and (t1.path / "faktura_2.pdf").read_bytes() == "druhá".encode("utf-8"))
check("_links s RELATIVNÍ cestou", [l["path"] for l in t1.links] == ["faktura.pdf", "faktura_2.pdf"]
      and all(l["name"] == "faktura.pdf" for l in t1.links))
check("link_path řeší relativní cestu vůči úkolu", Path(t1.link_path(t1.links[0])) == t1.path / "faktura.pdf")
check("link_path nechá absolutní cestu a URI", t1.link_path({"path": r"C:\x\y.txt"}) == r"C:\x\y.txt"
      and t1.link_path({"path": "content://a/b"}) == "content://a/b")
check("prázdný e-mail má prázdný popis", inbox.children[1].read_body() == "")
check("pořadí je globálně jedinečné", len({n.order for n in ws.all_nodes()}) == sum(1 for _ in ws.all_nodes()))
check("processed_uids = nové", res.processed_uids == ["1", "2"])

# druhé kolo: duplicita + nová zpráva bez Message-ID (ta se importuje vždy)
m3 = MailMessage("3", "", "Bez id", "", "", "x", [])
res2 = import_messages(ws, [m1, m3])
check("duplicita podle Message-ID se přeskočí", [m.uid for m in res2.duplicates] == ["1"] and len(res2.created) == 1)
check("_INBOX se znovu nezakládá", sum(1 for r in ws.roots if r.title.lower() == "_inbox") == 1)
check("duplicita se přesto označí jako přečtená", res2.processed_uids == ["3", "1"])

# duplicita přežije i reload z disku a přesun úkolu mimo _INBOX
ws.load()
moved = ws.node_by_id(t1.task_id)
ws.move_under(moved, ws.roots[0] if ws.roots[0].title == "Projekt" else ws.roots[1])
res3 = import_messages(ws, [m1])
check("Message-ID se hledá v celém prostoru (i po přesunu)", res3.created == [] and len(res3.duplicates) == 1)

# existující sekce v jiné velikosti písmen se použije
ws2 = Workspace(tmp / "ws2")
ws2.load()
old = ws2.create_root("_Inbox")
res4 = import_messages(ws2, [m2])
check("existující „_Inbox“ se použije místo nové sekce", res4.inbox is old and old.children[0].title == "Bez těla"
      and len(ws2.roots) == 1)
check("bez nových zpráv sekce nevzniká", import_messages(Workspace(tmp / "ws3"), []).inbox is None
      and not list((tmp / "ws3").iterdir()))

# --- 3) nastavení ---
print("3) MailSettings")
ini = QSettings(str(tmp / "mail.ini"), QSettings.Format.IniFormat)
d = MailSettings.load(ini, secure=False)
check("výchozí: seznam.cz, 993, SSL, adresa schránky", d.host == "imap.seznam.cz" and d.port == 993 and d.ssl
      and d.user == "dapar777_taskmaster@seznam.cz" and d.folder == "INBOX" and d.interval_min == 0)
check("bez hesla není nastavení úplné", not d.complete)
d.password = "tajne"
d.interval_min = 15
d.folder = "Ukoly"
d.save(ini, secure=False)
back = MailSettings.load(QSettings(str(tmp / "mail.ini"), QSettings.Format.IniFormat), secure=False)
check("uložení a načtení (bez Správce pověření)", back == d and back.complete)

# --- 4) průchod přes MainWindow s falešnou schránkou ---
print("4) MainWindow")


class FakeBox:
    instances = []

    def __init__(self, settings, messages):
        self.settings = settings
        self.messages = messages
        self.seen = []
        self.closed = False
        FakeBox.instances.append(self)

    def mark_seen(self, uid):
        self.seen.append(uid)

    def close(self):
        self.closed = True


pending = {"messages": [], "error": None}


def fake_fetch_unseen(settings, limit=100, mailbox_factory=None):
    if pending["error"]:
        raise mailimport.MailError(pending["error"])
    return FakeBox(settings, pending["messages"]), list(pending["messages"])


mailimport.fetch_unseen = fake_fetch_unseen

from app.mainwindow import MainWindow  # noqa: E402

win = MainWindow()
win.resize(1100, 700)
win.show()
QTest.qWaitForWindowExposed(win)
app.processEvents()
check("akce existují a mají zkratku", "mail.import" in win.act and "mail.settings" in win.act
      and win.act["mail.import"].shortcut().toString() == "Ctrl+Shift+M")
check("paleta má obě položky", {"Načíst úkoly z e-mailu", "Nastavení e-mailu…"} <= {e["label"] for e in win._build_palette_commands()})
check("s intervalem 0 je periodická kontrola vypnutá", not win._mail_timer.isActive())

win.mail_settings = MailSettings(password="x")


def wait_idle(ms=4000):
    for _ in range(ms // 20):
        app.processEvents()
        if win._mail_worker is None:
            app.processEvents()
            return True
        QTest.qWait(20)
    return False


pending["messages"] = [MailMessage("11", "<w1@x>", "Z okna", "a@b", "2026-09-08 09:00", "text", [("p.txt", b"obsah")]),
                       MailMessage("12", "<w2@x>", "Druhý", "", "", "", [])]
win.act["mail.import"].trigger()
check("import doběhl (obě vlákna)", wait_idle())
box = FakeBox.instances[-1]
inbox = mailimport.find_inbox(win.workspace)
check("úkoly vznikly v _INBOX hlavního okna", inbox is not None and [c.title for c in inbox.children] == ["Z okna", "Druhý"])
check("zprávy označené jako přečtené a schránka zavřená", box.seen == ["11", "12"] and box.closed)
check("první nový úkol je aktivní", win._current_node is not None and win._current_node.title == "Z okna")
from app.detailpanel import PATH_ROLE  # noqa: E402
item = win.detail.link_list.item(0) if win.detail.link_list.count() == 1 else None
check("příloha vidět v panelu odkazů a soubor existuje", item is not None and os.path.exists(item.data(PATH_ROLE)))
check("stavový řádek hlásí počet", "Načteno úkolů z e-mailu: 2" in win.status.currentMessage())

# opakování: nic nového, duplicity se označí
win.act["mail.import"].trigger()
check("druhý import doběhl", wait_idle())
check("duplicity nevytvoří nové úkoly", len(inbox.children) == 2 and FakeBox.instances[-1].seen == ["11", "12"])
check("hláška o duplicitách", "Žádné nové e-maily" in win.status.currentMessage())

# chyba sítě: jen stavový řádek (auto) / dialog (ručně – obejdeme)
from PySide6.QtWidgets import QMessageBox  # noqa: E402
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
pending["error"] = "Nelze se připojit"
win._import_mail_auto()
check("chybný import doběhl", wait_idle())
check("chyba ve stavovém řádku, úkoly beze změny", "Nelze se připojit" in win.status.currentMessage() and len(inbox.children) == 2)
pending["error"] = None

# periodická kontrola se zapne podle intervalu
win.mail_settings.interval_min = 5
win._apply_mail_timer()
check("timer běží s intervalem 5 min", win._mail_timer.isActive() and win._mail_timer.interval() == 5 * 60 * 1000)
win.mail_settings.interval_min = 0
win._apply_mail_timer()
check("interval 0 timer vypne", not win._mail_timer.isActive())

# undo posledního importu smaže nové úkoly (levný záznam „created")
win._undo()
app.processEvents()
check("undo importu smaže nové úkoly", not inbox.children or all(not c.path.exists() for c in inbox.children))

win.close()
print()
print("SELHALO: " + (", ".join(fails) if fails else "nic – vše prošlo"))
sys.exit(1 if fails else 0)
