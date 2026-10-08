"""Editor popisu nad Milkdown (Crepe) v QtWebEngine.

Stejné veřejné rozhraní jako `MarkdownEditor` (`editor.py`): signál
`contentChanged`, `command_actions` (cid -> QAction pro ShortcutManager),
`source_action`, `edit` (widget, kterému se dává fokus), `set_markdown`,
`to_markdown`, `clear`, `retheme`. Který editor se použije, rozhoduje
`create_editor()` podle QSettings `editor_engine`; bez QtWebEngine
(balík PySide6-Addons) nebo bez sestaveného bundlu se tiše vrátí QTextEdit.

Webová část je jeden soubor `app/webeditor/index.html` (zdroj `webeditor/`,
build `npm run build`), sdílený s Android klientem. Komunikace:
hostitel -> stránka přes `page.runJavaScript("TM....")`, stránka -> hostitel
přes QWebChannel objekt `TMHost` (`onReady`, `onChange(md)`).

`to_markdown()` musí být synchronní (detail ho volá při autosave i při
přepnutí úkolu), ale `runJavaScript` je asynchronní — proto si držíme
zrcadlo `_md`, které stránka aktualizuje při každé změně. Mezi posledním
úhozem a doručením `onChange` je okno v řádu milisekund; autosave (1,2 s)
ho s rezervou pokryje.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QFile, QIODevice, QObject, QSettings, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QInputDialog, QPlainTextEdit, QStackedWidget, QToolBar, QVBoxLayout, QWidget

from . import theme
from .constants import APP_NAME, ORG_NAME
from .editor import MarkdownEditor

ENGINE_QT = "qt"
ENGINE_MILKDOWN = "milkdown"
#: (klíč, popisek) – pořadí = pořadí v Nastavení a v paletě
ENGINES = (
    (ENGINE_MILKDOWN, "Milkdown (WYSIWYG)"),
    (ENGINE_QT, "Qt (původní)"),
)
DEFAULT_ENGINE = ENGINE_MILKDOWN

BUNDLE = Path(__file__).with_name("webeditor") / "index.html"


def webengine_available() -> bool:
    """QtWebEngine je nainstalovaný (PySide6-Addons), byl importovaný **před**
    vznikem QApplication a bundle existuje.

    Qt vyžaduje import `QtWebEngineWidgets` (a `AA_ShareOpenGLContexts`) ještě
    před aplikací; pozdní import se zdánlivě povede, ale proces pak padá při
    ukončení (segfault při úklidu Chromia). `main.py` import dělá; skript nebo
    test, který ho neudělal, dostane Qt editor místo pádu.
    """
    app = QCoreApplication.instance()
    if app is not None:
        if "PySide6.QtWebEngineWidgets" not in sys.modules:
            return False
        if not QCoreApplication.testAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts):
            return False
    try:
        import PySide6.QtWebChannel  # noqa: F401
        import PySide6.QtWebEngineWidgets  # noqa: F401
    except ImportError:
        return False
    return BUNDLE.is_file()


def configured_engine(settings: QSettings | None = None) -> str:
    s = settings or QSettings(ORG_NAME, APP_NAME)
    value = s.value("editor_engine", DEFAULT_ENGINE, type=str)
    return value if value in dict(ENGINES) else DEFAULT_ENGINE


def create_editor(parent=None, settings: QSettings | None = None):
    """Editor podle nastavení; Milkdown jen když je k dispozici, jinak Qt."""
    if configured_engine(settings) == ENGINE_MILKDOWN and webengine_available():
        return MilkdownEditor(parent)
    return MarkdownEditor(parent)


class _Host(QObject):
    """Objekt vystavený stránce přes QWebChannel (`window.TMHost`)."""

    changed = Signal(str)
    ready = Signal()

    @Slot(str)
    def onChange(self, md: str) -> None:  # noqa: N802 – název je rozhraní stránky
        self.changed.emit(md)

    @Slot()
    def onReady(self) -> None:  # noqa: N802
        self.ready.emit()


def _qwebchannel_js() -> str:
    """qwebchannel.js z Qt resources (registruje se importem QtWebChannel)."""
    import PySide6.QtWebChannel  # noqa: F401

    f = QFile(":/qtwebchannel/qwebchannel.js")
    if not f.open(QIODevice.OpenModeFlag.ReadOnly):
        raise RuntimeError("qwebchannel.js není v Qt resources")
    try:
        return bytes(f.readAll()).decode("utf-8")
    finally:
        f.close()


def drain_deferred(app, ms: int = 300) -> None:
    """Nechá doběhnout odložená mazání (deleteLater) a zprávy Chromia.

    QtWebEngine potřebuje po `deleteLater()` stránky ještě pár otáček smyčky,
    aby ukončil renderer; jediné `processEvents()` nestačí a proces pak
    při rozpadu objektů padá (0xC0000005). Volá se z `main.py` po `app.exec()`
    a z testů před koncem.
    """
    import time

    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.processEvents()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        time.sleep(0.01)


def theme_vars() -> dict[str, str]:
    """CSS proměnné pro stránku z aktuálního tématu a zoomu (jediný zdroj barev je theme.py)."""
    t = theme.current()
    return {
        "--crepe-color-background": t.canvas,
        "--crepe-color-on-background": t.text,
        "--crepe-color-surface": t.paper,
        "--crepe-color-surface-low": t.panel,
        "--crepe-color-on-surface": t.text,
        "--crepe-color-on-surface-variant": t.text2,
        "--crepe-color-outline": t.border,
        "--crepe-color-primary": t.accent,
        "--crepe-color-secondary": t.selection,
        "--crepe-color-on-secondary": t.text,
        "--crepe-color-inverse": t.text,
        "--crepe-color-on-inverse": t.canvas,
        "--crepe-color-inline-code": t.accent,
        "--crepe-color-error": t.status_dot.get("blocked", t.accent),
        "--crepe-color-hover": t.hover,
        "--crepe-color-selected": t.selection,
        "--crepe-color-inline-area": t.panel,
        "--crepe-font-title": ", ".join(theme.TITLE_FAMILIES),
        "--crepe-font-default": ", ".join(theme.UI_FAMILIES),
        "--crepe-font-code": ", ".join(theme.MONO_FAMILIES),
        # 11 pt základního písma editoru QTextEdit ≈ 15 px; px() násobí zoomem.
        # Crepe od téhle hodnoty odvozuje i vlastní rozměry (nadpisy, menu).
        "--crepe-base-font-size": f"{theme.px(15)}px",
        "--tm-font-size": f"{theme.px(15)}px",
        "--tm-pad": f"{theme.px(12)}px",
    }


class MilkdownEditor(QWidget):
    contentChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._md = ""
        self._pending: str | None = None  # obsah čekající na onReady
        self._ready = False
        self._source_mode = False
        self.command_actions: dict[str, QAction] = {}
        self.console_messages: list[str] = []  # JS konzole stránky (diagnostika, testy)

        owner = self

        class _Page(QWebEnginePage):
            def javaScriptConsoleMessage(self, level, message, line, source_id):  # noqa: N802
                owner.console_messages.append(f"{message} ({source_id}:{line})")

        class _View(QWebEngineView):
            """setFocus dá fokus i kurzoru ve stránce (MainWindow volá editor.edit.setFocus())."""

            def setFocus(self, *args):  # noqa: N802
                super().setFocus(*args)
                self.page().runJavaScript("window.TM && window.TM.focus()")

        self.view = _View(self)
        self.view.setPage(_Page(self.view))
        # Chromium má vlastní (anglické) kontextové menu – formátování řeší lišta a Crepe
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.view.installEventFilter(self)
        self.view.loadFinished.connect(self._on_load_finished)

        # most stránka -> Python
        self._host = _Host(self)
        self._host.changed.connect(self._on_page_changed)
        self._host.ready.connect(self._on_page_ready)
        self._channel = QWebChannel(self.view.page())
        self._channel.registerObject("TMHost", self._host)
        self.view.page().setWebChannel(self._channel)

        # qwebchannel.js při vzniku dokumentu, navázání kanálu po DOMContentLoaded
        # (modulový skript stránky už proběhl, window.TM existuje)
        scripts = self.view.page().scripts()
        s1 = QWebEngineScript()
        s1.setName("qwebchannel")
        s1.setSourceCode(_qwebchannel_js())
        s1.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        s1.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        s1.setRunsOnSubFrames(False)
        scripts.insert(s1)
        s2 = QWebEngineScript()
        s2.setName("tm-bind")
        s2.setSourceCode(
            "new QWebChannel(qt.webChannelTransport, function (ch) { window.TM.bind(ch.objects.TMHost); });"
        )
        s2.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        s2.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        s2.setRunsOnSubFrames(False)
        scripts.insert(s2)

        # zdrojový markdown (parita s `view.toggle_source`)
        self.source_edit = QPlainTextEdit(self)
        self.source_edit.setFont(theme.mono_font(10))
        self.source_edit.textChanged.connect(self._on_source_changed)

        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.view)
        self.stack.addWidget(self.source_edit)

        self.toolbar = QToolBar()
        self._build_toolbar()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.stack, 1)

        self.view.load(QUrl.fromLocalFile(str(BUNDLE)))

        # stránku (a objekt kanálu) je nutné odpojit a smazat ještě za běhu
        # aplikace – kdyby ji uklízel až Python při rozpadu objektů po konci
        # `app.exec()`, Chromium spadne (viz drain_deferred)
        self._shut = False
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def shutdown(self) -> None:
        """Odpojí most a nechá stránku i pohled smazat; bezpečné volat vícekrát."""
        if self._shut:
            return
        self._shut = True
        self._ready = False
        page = self.view.page()
        try:
            page.setWebChannel(None)
        except Exception:  # noqa: BLE001 – při částečně rozpadlém objektu nic nerozbít
            pass
        page.deleteLater()
        self.view.deleteLater()

    # ------------------------------------------------------------------
    # Rozhraní shodné s MarkdownEditor
    # ------------------------------------------------------------------
    @property
    def edit(self) -> QWidget:
        """Widget, který má dostat fokus (podle režimu web / zdroj)."""
        return self.source_edit if self._source_mode else self.view

    def is_ready(self) -> bool:
        return self._ready

    def set_markdown(self, text: str) -> None:
        text = text or ""
        if self.source_action.isChecked():
            self.source_action.setChecked(False)  # vrátí do WYSIWYG
        self._md = text
        if self._ready:
            self._js(f"window.TM.setMarkdown({json.dumps(text)})")
        else:
            self._pending = text

    def to_markdown(self) -> str:
        if self._source_mode:
            return self.source_edit.toPlainText()
        return self._md

    def clear(self) -> None:
        self.set_markdown("")

    def retheme(self) -> None:
        """Po změně tématu nebo zoomu: nové barvy a velikosti do stránky."""
        self.source_edit.setFont(theme.mono_font(10))
        if self._ready:
            self._push_theme()

    # ------------------------------------------------------------------
    # Lišta – stejné cid jako MarkdownEditor (zkratky přiřadí ShortcutManager)
    # ------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        tb = self.toolbar
        self._format_actions: list[QAction] = []

        def add(cid, text, tip, slot, checkable=False):
            act = QAction(text, self)
            act.setToolTip(tip)
            act.setCheckable(checkable)
            act.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            if slot is not None:
                act.triggered.connect(slot)
            tb.addAction(act)
            self.addAction(act)
            self.command_actions[cid] = act
            if cid != "view.toggle_source":
                self._format_actions.append(act)
            return act

        def ex(cid):
            return lambda: self.exec(cid)

        add("fmt.bold", "B", "Tučné", ex("fmt.bold"))
        add("fmt.italic", "I", "Kurzíva", ex("fmt.italic"))
        add("fmt.strike", "S̶", "Přeškrtnuté", ex("fmt.strike"))
        add("fmt.code", "</>", "Inline kód", ex("fmt.code"))
        tb.addSeparator()
        add("fmt.h1", "H1", "Nadpis 1", ex("fmt.h1"))
        add("fmt.h2", "H2", "Nadpis 2", ex("fmt.h2"))
        add("fmt.h3", "H3", "Nadpis 3", ex("fmt.h3"))
        add("fmt.paragraph", "¶", "Normální odstavec", ex("fmt.paragraph"))
        tb.addSeparator()
        add("fmt.bullet", "•", "Odrážkový seznam", ex("fmt.bullet"))
        add("fmt.numbered", "1.", "Číslovaný seznam", ex("fmt.numbered"))
        add("fmt.quote", "❝", "Citace (blockquote)", ex("fmt.quote"))
        add("fmt.hr", "―", "Vodorovná čára", ex("fmt.hr"))
        tb.addSeparator()
        add("fmt.link", "🔗", "Vložit odkaz", self._link)
        tb.addSeparator()
        self.source_action = add("view.toggle_source", "MD", "Přepnout na zdrojový markdown", None, checkable=True)
        self.source_action.toggled.connect(self._toggle_source)

    def exec(self, cid: str, arg=None) -> None:
        """Formátovací příkaz stránky (`fmt.*`); ve zdrojovém režimu nic."""
        if self._source_mode or not self._ready:
            return
        payload = "" if arg is None else ", " + json.dumps(arg)
        self._js(f"window.TM.exec({json.dumps(cid)}{payload})")

    def _link(self) -> None:
        url, ok = QInputDialog.getText(self, "Vložit odkaz", "URL:", text="https://")
        if ok and url:
            self.exec("fmt.link", url)

    def _toggle_source(self, on: bool) -> None:
        if on:
            self.source_edit.blockSignals(True)
            self.source_edit.setPlainText(self._md)
            self.source_edit.blockSignals(False)
            self._source_mode = True
            self.stack.setCurrentWidget(self.source_edit)
        else:
            md = self.source_edit.toPlainText()
            self._source_mode = False
            self.stack.setCurrentWidget(self.view)
            if md != self._md:
                self._md = md
                if self._ready:
                    self._js(f"window.TM.setMarkdown({json.dumps(md)})")
                else:
                    self._pending = md
        for act in self._format_actions:
            act.setEnabled(not on)

    # ------------------------------------------------------------------
    # Most
    # ------------------------------------------------------------------
    def _js(self, code: str) -> None:
        self.view.page().runJavaScript(code)

    def _push_theme(self) -> None:
        self._js(f"window.TM.setTheme({json.dumps(theme_vars())})")

    def _on_load_finished(self, ok: bool) -> None:
        # Chromium vytvoří vnitřní widget až po načtení – teprve ten dostává klávesy
        proxy = self.view.focusProxy()
        if proxy is not None:
            proxy.installEventFilter(self)

    def _on_page_ready(self) -> None:
        self._ready = True
        self._push_theme()
        pending = self._pending if self._pending is not None else self._md
        self._pending = None
        self._js(f"window.TM.setMarkdown({json.dumps(pending)})")

    def _on_page_changed(self, md: str) -> None:
        if md == self._md:
            return
        self._md = md
        self.contentChanged.emit()

    def _on_source_changed(self) -> None:
        if self._source_mode:
            self.contentChanged.emit()

    # ------------------------------------------------------------------
    # Průchodnost globálních zkratek (parita s _BodyTextEdit)
    # ------------------------------------------------------------------
    def eventFilter(self, obj, e) -> bool:  # noqa: N802
        if e.type() == QEvent.Type.ShortcutOverride and self._release_to_window(e.keyCombination()):
            e.ignore()
            return True
        return super().eventFilter(obj, e)

    def _release_to_window(self, combo) -> bool:
        """Klávesu přenechat globální zkratce okna, pokud ji používá akce
        s kontextem celého okna a nekoliduje s vlastní zkratkou editoru."""
        seq = QKeySequence(combo)
        if seq.isEmpty():
            return False
        for act in self.command_actions.values():
            s = act.shortcut()
            if not s.isEmpty() and s == seq:
                return False
        win = self.window()
        if win is None:
            return False
        for act in win.findChildren(QAction):
            if not act.isEnabled() or act.shortcutContext() != Qt.ShortcutContext.WindowShortcut:
                continue
            s = act.shortcut()
            if not s.isEmpty() and s == seq:
                return True
        return False
