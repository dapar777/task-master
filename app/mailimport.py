"""Načítání úkolů z e-mailové schránky (IMAP) do sekce ``_INBOX``.

Každý nepřečtený e-mail = jeden úkol pod kořenovou sekcí ``_INBOX`` (založí
se, když chybí; existující ``_Inbox`` v libovolné velikosti písmen se použije):
název = předmět, popis = odesílatel, datum a text zprávy (HTML se převede na
markdown), přílohy se uloží do adresáře úkolu a zapíšou do ``_links``
s RELATIVNÍ cestou – stejně jako přílohy z Android klienta, takže fungují
v obou aplikacích i po synchronizaci prostoru.

Zpracovaná zpráva se na serveru označí jako přečtená; proti opakovanému
importu (ruční „označit jako nepřečtené", druhá aplikace nad stejným
prostorem) navíc chrání klíč ``_mail_id`` (Message-ID) v metadatech úkolu –
obě aplikace neznámé klíče zachovávají.

Síťová část (:class:`ImapMailbox`) je oddělená od zpracování
(:func:`parse_message`, :func:`import_messages`), aby se import dal testovat
bez serveru. Hlavní okno volá síť ve vlákně (:class:`MailWorker`) a úkoly
zakládá v hlavním vlákně – paměťový strom není thread-safe.
"""

from __future__ import annotations

import email
import email.policy
import email.utils
import imaplib
import re
import ssl
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, Signal

from .htmlmd import html_to_markdown
from .storage import TaskNode, Workspace, now_iso

INBOX_TITLE = "_INBOX"
MAIL_ID_KEY = "_mail_id"
DEFAULT_HOST = "imap.seznam.cz"
DEFAULT_PORT = 993
DEFAULT_USER = "dapar777_taskmaster@seznam.cz"
NO_SUBJECT = "(bez předmětu)"
FETCH_LIMIT = 100  # zpráv na jeden import (ochrana před přeplněnou schránkou)
_CRED_TARGET = "TaskMaster/mail"  # záznam ve Správci pověření Windows


class MailError(Exception):
    """Srozumitelná chyba pro uživatele (připojení, přihlášení, složka)."""


# ----------------------------------------------------------------------
# Nastavení
# ----------------------------------------------------------------------
def _cred_write(user: str, password: str) -> bool:
    """Heslo do Správce pověření Windows (pywin32); False = není k dispozici."""
    try:
        import win32cred  # noqa: WPS433
    except ImportError:
        return False
    try:
        win32cred.CredWrite({
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": _CRED_TARGET,
            "UserName": user or "",
            "CredentialBlob": password or "",
            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
        }, 0)
        return True
    except Exception:
        return False


def _cred_read() -> str | None:
    """Heslo ze Správce pověření; None = záznam nebo pywin32 chybí."""
    try:
        import win32cred  # noqa: WPS433
    except ImportError:
        return None
    try:
        cred = win32cred.CredRead(_CRED_TARGET, win32cred.CRED_TYPE_GENERIC)
    except Exception:
        return None
    blob = cred.get("CredentialBlob")
    if isinstance(blob, (bytes, bytearray)):
        return bytes(blob).decode("utf-16-le", errors="ignore")
    return str(blob or "")


@dataclass
class MailSettings:
    """Připojení ke schránce. Heslo jde do Správce pověření (když je pywin32),
    ostatní do QSettings; ``interval_min`` 0 = automatická kontrola vypnutá."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    ssl: bool = True
    user: str = DEFAULT_USER
    password: str = ""
    folder: str = "INBOX"
    interval_min: int = 0

    @property
    def complete(self) -> bool:
        return bool(self.host.strip() and self.user.strip() and self.password)

    @classmethod
    def load(cls, qs: QSettings, secure: bool = True) -> "MailSettings":
        s = cls(
            host=(qs.value("mail_host", DEFAULT_HOST, type=str) or DEFAULT_HOST).strip(),
            port=int(qs.value("mail_port", DEFAULT_PORT, type=int) or DEFAULT_PORT),
            ssl=bool(qs.value("mail_ssl", True, type=bool)),
            user=(qs.value("mail_user", DEFAULT_USER, type=str) or DEFAULT_USER).strip(),
            folder=(qs.value("mail_folder", "INBOX", type=str) or "INBOX").strip(),
            interval_min=max(0, int(qs.value("mail_interval_min", 0, type=int) or 0)),
        )
        pw = _cred_read() if secure else None
        s.password = pw if pw is not None else (qs.value("mail_password", "", type=str) or "")
        return s

    def save(self, qs: QSettings, secure: bool = True) -> None:
        qs.setValue("mail_host", self.host.strip())
        qs.setValue("mail_port", int(self.port))
        qs.setValue("mail_ssl", bool(self.ssl))
        qs.setValue("mail_user", self.user.strip())
        qs.setValue("mail_folder", self.folder.strip() or "INBOX")
        qs.setValue("mail_interval_min", max(0, int(self.interval_min)))
        if secure and _cred_write(self.user, self.password):
            qs.remove("mail_password")  # heslo je ve Správci pověření, ne v registru
        else:
            qs.setValue("mail_password", self.password)
        qs.sync()


# ----------------------------------------------------------------------
# Zpráva -> data úkolu
# ----------------------------------------------------------------------
@dataclass
class MailMessage:
    uid: str
    message_id: str
    subject: str
    sender: str
    date: str          # lokální čas „YYYY-MM-DD HH:MM" (nebo původní text)
    text: str          # tělo jako markdown / prostý text
    attachments: list = field(default_factory=list)  # [(název souboru, bytes)]


_INVALID_FILE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str, fallback: str = "priloha") -> str:
    """Název souboru přílohy bezpečný pro Windows (bez cesty a zakázaných znaků)."""
    name = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = _INVALID_FILE.sub("", name.strip()).strip(". ")
    name = re.sub(r"\s+", "_", name)
    return name or fallback


def unique_filename(folder: Path, name: str) -> str:
    """Zajistí, že soubor v adresáři ještě neexistuje (``x_2.pdf``, ``x_3.pdf``…)."""
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        stem, ext = name, ""
    else:
        ext = "." + ext
    candidate, i = name, 2
    while (folder / candidate).exists():
        candidate = f"{stem}_{i}{ext}"
        i += 1
    return candidate


def _format_date(value) -> str:
    if not value:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(str(value))
    except Exception:
        return str(value).strip()
    try:
        if dt.tzinfo is not None:
            dt = dt.astimezone()  # do lokálního času
    except Exception:
        pass
    return dt.strftime("%Y-%m-%d %H:%M")


def parse_message(uid: str, raw: bytes) -> MailMessage:
    """Z RFC 822 zprávy vytáhne předmět, odesílatele, datum, tělo a přílohy.

    Tělo: přednost má ``text/plain``, jinak ``text/html`` převedené na markdown.
    Příloha = každá nemultipart část mimo zvolené tělo, která má název souboru
    nebo ``Content-Disposition: attachment`` (včetně vložených obrázků).
    """
    msg = email.message_from_bytes(raw or b"", policy=email.policy.default)
    subject = re.sub(r"\s+", " ", str(msg.get("subject", "") or "")).strip() or NO_SUBJECT
    sender = str(msg.get("from", "") or "").strip()
    message_id = str(msg.get("message-id", "") or "").strip()
    try:
        body_part = msg.get_body(preferencelist=("plain", "html"))
    except Exception:
        body_part = None
    text = ""
    if body_part is not None:
        try:
            content = body_part.get_content()
        except Exception:
            content = ""
        if not isinstance(content, str):
            content = ""
        if body_part.get_content_type() == "text/html":
            text = html_to_markdown(content)
        else:
            text = content.replace("\r\n", "\n").strip()
    attachments = []
    for part in msg.walk():
        if part.is_multipart() or part is body_part:
            continue
        fname = part.get_filename()
        if not fname and part.get_content_disposition() != "attachment":
            continue
        try:
            data = part.get_payload(decode=True)
        except Exception:
            data = None
        if data is None:
            continue
        attachments.append((str(fname or "").strip() or "priloha", bytes(data)))
    return MailMessage(str(uid), message_id, subject, sender, _format_date(msg.get("date")),
                       text, attachments)


def task_body(msg: MailMessage) -> str:
    """Popis úkolu: hlavička (odesílatel, datum) a text zprávy."""
    head = []
    if msg.sender:
        head.append(f"**Od:** {msg.sender}")
    if msg.date:
        head.append(f"**Datum:** {msg.date}")
    parts = ["  \n".join(head)] if head else []
    if msg.text:
        parts.append(msg.text)
    return ("\n\n".join(parts) + "\n") if parts else ""


# ----------------------------------------------------------------------
# Založení úkolů ve workspace (hlavní vlákno, bez sítě)
# ----------------------------------------------------------------------
@dataclass
class ImportResult:
    inbox: TaskNode | None
    created: list = field(default_factory=list)     # [(MailMessage, TaskNode)]
    duplicates: list = field(default_factory=list)  # [MailMessage] – už importované

    @property
    def processed_uids(self) -> list[str]:
        """UID zpráv, které se mají označit jako přečtené (nové i duplicitní)."""
        return [m.uid for m, _ in self.created] + [m.uid for m in self.duplicates]


def find_inbox(workspace: Workspace, title: str = INBOX_TITLE) -> TaskNode | None:
    """Kořenová sekce pro e-maily; velikost písmen nerozhoduje (``_Inbox``)."""
    want = title.strip().lower()
    for n in workspace.roots:
        if n.title.strip().lower() == want:
            return n
    return None


def ensure_inbox(workspace: Workspace, title: str = INBOX_TITLE) -> TaskNode:
    return find_inbox(workspace, title) or workspace.create_root(title)


def known_mail_ids(workspace: Workspace) -> set[str]:
    return {str(n.meta.get(MAIL_ID_KEY)) for n in workspace.all_nodes() if n.meta.get(MAIL_ID_KEY)}


def import_messages(workspace: Workspace, messages: list[MailMessage],
                    section: str = INBOX_TITLE) -> ImportResult:
    """Založí úkoly z e-mailů pod sekci (vznikne až s první novou zprávou).

    Nové úkoly jdou rovnou do paměťového stromu (``create_child_of``) –
    volající po nich ``load()`` nevolá. Duplicitní Message-ID se přeskočí.
    """
    known = known_mail_ids(workspace)
    inbox = find_inbox(workspace, section)
    result = ImportResult(inbox)
    for m in messages:
        if m.message_id and m.message_id in known:
            result.duplicates.append(m)
            continue
        if inbox is None:
            inbox = ensure_inbox(workspace, section)
            result.inbox = inbox
        node = workspace.create_child_of(inbox, (m.subject or "").strip() or NO_SUBJECT)
        links = node.meta.setdefault("_links", [])
        for name, data in m.attachments:
            fname = unique_filename(node.path, safe_filename(name))
            try:
                (node.path / fname).write_bytes(data)
            except OSError:
                continue
            links.append({"name": name or fname, "path": fname, "added": now_iso()})
        if m.message_id:
            node.meta[MAIL_ID_KEY] = m.message_id
            known.add(m.message_id)
        node.save_meta()
        node.write_body(task_body(m))
        result.created.append((m, node))
    return result


# ----------------------------------------------------------------------
# IMAP
# ----------------------------------------------------------------------
class ImapMailbox:
    """Tenký obal nad imaplib: nepřečtené UID, stažení zprávy, označení jako přečtené."""

    def __init__(self, settings: MailSettings, timeout: float = 20.0):
        self.settings = settings
        self.timeout = timeout
        self.conn = None

    def open(self) -> "ImapMailbox":
        s = self.settings
        try:
            if s.ssl:
                conn = imaplib.IMAP4_SSL(s.host, int(s.port), timeout=self.timeout)
            else:
                conn = imaplib.IMAP4(s.host, int(s.port), timeout=self.timeout)
        except (OSError, ssl.SSLError) as ex:  # gaierror, timeout, odmítnuté spojení…
            raise MailError(f"Nelze se připojit k {s.host}:{s.port} ({ex})") from ex
        try:
            conn.login(s.user, s.password)
        except imaplib.IMAP4.error as ex:
            _quiet(conn.logout)
            raise MailError(f"Přihlášení k {s.user} selhalo – zkontroluj jméno a heslo "
                            f"(a že je IMAP ve schránce povolený). {ex}") from ex
        typ, _ = conn.select(s.folder or "INBOX")
        if typ != "OK":
            _quiet(conn.logout)
            raise MailError(f"Složku „{s.folder}“ nejde otevřít")
        self.conn = conn
        return self

    def unseen_uids(self) -> list[str]:
        typ, data = self.conn.uid("SEARCH", None, "UNSEEN")
        if typ != "OK":
            raise MailError("Hledání nepřečtených zpráv selhalo")
        return [u.decode("ascii", "ignore") for u in (data[0] or b"").split()]

    def fetch(self, uid: str) -> bytes:
        typ, data = self.conn.uid("FETCH", uid, "(BODY.PEEK[])")
        if typ != "OK":
            raise MailError(f"Zprávu {uid} nejde stáhnout")
        for item in data or ():
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
                return bytes(item[1])
        raise MailError(f"Zpráva {uid} přišla v neznámém formátu")

    def mark_seen(self, uid: str) -> None:
        self.conn.uid("STORE", uid, "+FLAGS", "(\\Seen)")

    def close(self) -> None:
        if self.conn is None:
            return
        _quiet(self.conn.close)
        _quiet(self.conn.logout)
        self.conn = None


def _quiet(fn) -> None:
    try:
        fn()
    except Exception:
        pass


def fetch_unseen(settings: MailSettings, limit: int = FETCH_LIMIT,
                 mailbox_factory=ImapMailbox) -> tuple[ImapMailbox, list[MailMessage]]:
    """Otevře schránku a stáhne nepřečtené zprávy (síť – volat z vlákna).

    Schránku vrací OTEVŘENOU: po založení úkolů ji :func:`finish` označí
    zprávy jako přečtené a zavře. Při chybě se zavře tady.
    """
    box = mailbox_factory(settings).open()
    try:
        uids = box.unseen_uids()[:limit]
        messages = [parse_message(u, box.fetch(u)) for u in uids]
    except Exception as ex:
        box.close()
        if isinstance(ex, MailError):
            raise
        raise MailError(f"Stahování zpráv selhalo ({ex})") from ex
    return box, messages


def finish(box, uids: list[str]) -> int:
    """Označí zpracované zprávy jako přečtené a zavře schránku (síť – vlákno)."""
    try:
        for u in uids:
            box.mark_seen(u)
    except Exception as ex:
        raise MailError(f"Označení zpráv jako přečtených selhalo ({ex})") from ex
    finally:
        box.close()
    return len(uids)


def test_connection(settings: MailSettings) -> str:
    """Ověří přihlášení a spočítá nepřečtené zprávy (síť – vlákno)."""
    box = ImapMailbox(settings).open()
    try:
        n = len(box.unseen_uids())
    finally:
        box.close()
    return f"Připojení funguje – nepřečtených zpráv: {n}"


class MailWorker(QThread):
    """Spustí funkci ve vlákně; ``done(výsledek, chyba)`` – chyba je text nebo None."""

    done = Signal(object, object)

    def __init__(self, fn, *args, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._args = args

    def run(self) -> None:
        try:
            self.done.emit(self._fn(*self._args), None)
        except Exception as ex:  # noqa: BLE001 – do UI jde jen text
            self.done.emit(None, str(ex) or type(ex).__name__)
