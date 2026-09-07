"""WYSIWYG editor markdownu postavený nad QTextEdit.

Edituje se formátovaný text (tučné, kurzíva, nadpisy, seznamy, odkazy...),
ukládá se jako markdown (QTextEdit.toMarkdown / setMarkdown).
Lze přepnout na zobrazení zdrojového markdownu.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QKeySequence,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
    QTextListFormat,
)
from PySide6.QtWidgets import (
    QInputDialog,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from . import theme

# nadpis -> FontSizeAdjustment (stupně relativní velikosti Qt: 3 = 2×, 2 = 1.5×, 1 = 1.2×)
_HEADING_ADJUST = {1: 3, 2: 2, 3: 1, 4: 0, 5: 0, 6: 0}


class _BodyTextEdit(QTextEdit):
    """QTextEdit, který nepohltí klávesové zkratky patřící celému oknu.

    QTextEdit si přes událost ShortcutOverride nárokuje řadu kombinací (např.
    Ctrl+J = řádkování/LF), takže globální zkratky okna (uložené filtry, přechod
    na hledání…) při psaní nefungují. Tady takový override uvolníme – ale jen
    pokud zkratka nekoliduje s vlastní zkratkou editoru (tučné, kurzíva…).
    """

    def __init__(self, owner: "MarkdownEditor"):
        super().__init__()
        self._owner = owner

    def event(self, e):
        if e.type() == QEvent.Type.ShortcutOverride:
            if self._owner._release_to_window(e.keyCombination()):
                e.ignore()
                return True
        return super().event(e)


class MarkdownEditor(QWidget):
    contentChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source_mode = False
        self._base_point = 11
        # zkratky editoru (vyplní _build_toolbar); potřebuje je _release_to_window
        self.command_actions: dict[str, QAction] = {}

        self.edit = _BodyTextEdit(self)
        self.edit.setAcceptRichText(True)
        self.edit.document().setDefaultFont(self._doc_font())
        self.edit.setTabChangesFocus(False)
        self.edit.textChanged.connect(self.contentChanged)

        self.toolbar = QToolBar()
        self._build_toolbar()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.edit, 1)

    def _doc_font(self) -> QFont:
        """Základní písmo těla; velikost jde přes zoom tématu."""
        f = QFont("Segoe UI")
        f.setPointSizeF(theme.pt(self._base_point))
        return f

    def retheme(self) -> None:
        """Po zoomu: nové základní písmo dokumentu. Nadpisy mají velikost
        relativní (FontSizeAdjustment jako import markdownu), takže se
        přeškálují s ním."""
        self.edit.document().setDefaultFont(self._doc_font())

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        tb = self.toolbar

        self._format_actions: list[QAction] = []
        # command_id -> QAction; zkratky přiřazuje ShortcutManager z hlavního okna
        # (dict už vznikl v __init__ kvůli _release_to_window)

        def add(cid, text, tip, slot, checkable=False):
            act = QAction(text, self)
            act.setToolTip(tip)
            act.setCheckable(checkable)
            # zkratky editoru jsou aktivní jen když má fokus editor
            act.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            if slot is not None:
                act.triggered.connect(slot)
            tb.addAction(act)
            self.addAction(act)  # nutné, aby fungovala zkratka při psaní v editoru
            self.command_actions[cid] = act
            if cid != "view.toggle_source":
                self._format_actions.append(act)
            return act

        add("fmt.bold", "B", "Tučné", self._bold)
        add("fmt.italic", "I", "Kurzíva", self._italic)
        add("fmt.strike", "S̶", "Přeškrtnuté", self._strike)
        add("fmt.code", "</>", "Inline kód", self._code)
        tb.addSeparator()
        add("fmt.h1", "H1", "Nadpis 1", lambda: self._heading(1))
        add("fmt.h2", "H2", "Nadpis 2", lambda: self._heading(2))
        add("fmt.h3", "H3", "Nadpis 3", lambda: self._heading(3))
        add("fmt.paragraph", "¶", "Normální odstavec", lambda: self._heading(0))
        tb.addSeparator()
        add("fmt.bullet", "•", "Odrážkový seznam", lambda: self._list(QTextListFormat.Style.ListDisc))
        add("fmt.numbered", "1.", "Číslovaný seznam", lambda: self._list(QTextListFormat.Style.ListDecimal))
        add("fmt.quote", "❝", "Citace (blockquote)", self._quote)
        add("fmt.hr", "―", "Vodorovná čára", self._hr)
        tb.addSeparator()
        add("fmt.link", "🔗", "Vložit odkaz", self._link)

        tb.addSeparator()
        self.source_action = add("view.toggle_source", "MD", "Přepnout na zdrojový markdown", None, checkable=True)
        self.source_action.toggled.connect(self._toggle_source)

    # ------------------------------------------------------------------
    # Průchodnost globálních zkratek
    # ------------------------------------------------------------------
    def _release_to_window(self, combo) -> bool:
        """Má se klávesa přenechat globální zkratce okna místo editoru?

        Ano, pokud ji používá nějaká akce s kontextem celého okna (WindowShortcut)
        a přitom nekoliduje s vlastní zkratkou editoru.
        """
        seq = QKeySequence(combo)
        if seq.isEmpty():
            return False
        # kolize s vlastní zkratkou editoru -> nechat editoru (uživatelovo pravidlo)
        for act in self.command_actions.values():
            s = act.shortcut()
            if not s.isEmpty() and s == seq:
                return False
        win = self.window()
        if win is None:
            return False
        for act in win.findChildren(QAction):
            if not act.isEnabled():
                continue
            if act.shortcutContext() != Qt.ShortcutContext.WindowShortcut:
                continue
            s = act.shortcut()
            if not s.isEmpty() and s == seq:
                return True
        return False

    # ------------------------------------------------------------------
    # Pomocné formátování
    # ------------------------------------------------------------------
    def _merge_char(self, fmt: QTextCharFormat) -> None:
        cursor = self.edit.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        cursor.mergeCharFormat(fmt)
        self.edit.mergeCurrentCharFormat(fmt)

    def _bold(self) -> None:
        fmt = QTextCharFormat()
        weight = QFont.Weight.Normal if self.edit.fontWeight() > QFont.Weight.Normal else QFont.Weight.Bold
        fmt.setFontWeight(weight)
        self._merge_char(fmt)

    def _italic(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self.edit.fontItalic())
        self._merge_char(fmt)

    def _strike(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(not self.edit.currentCharFormat().fontStrikeOut())
        self._merge_char(fmt)

    def _code(self) -> None:
        cur = self.edit.currentCharFormat()
        on = not cur.fontFixedPitch()
        fmt = QTextCharFormat()
        fmt.setFontFixedPitch(on)
        if on:
            fmt.setFontFamilies(["Consolas", "Courier New", "monospace"])
            fmt.setBackground(QColor(theme.current().panel))
        else:
            fmt.setFontFamilies(["Segoe UI"])
            fmt.setBackground(QColor("transparent"))
        self._merge_char(fmt)

    def _heading(self, level: int) -> None:
        cursor = self.edit.textCursor()
        cursor.beginEditBlock()
        block_fmt = cursor.blockFormat()
        block_fmt.setHeadingLevel(level)
        cursor.setBlockFormat(block_fmt)

        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        char_fmt = QTextCharFormat()
        # velikost relativní k základnímu písmu (stejně jako setMarkdown), ať
        # nadpis přežije zoom; absolutní body by po zoomu zůstaly staré
        char_fmt.setFontWeight(QFont.Weight.Normal if level == 0 else QFont.Weight.Bold)
        char_fmt.setProperty(QTextFormat.Property.FontSizeAdjustment,
                             _HEADING_ADJUST.get(level, 0))
        cursor.mergeCharFormat(char_fmt)
        cursor.endEditBlock()

    def _list(self, style) -> None:
        cursor = self.edit.textCursor()
        cursor.createList(QTextListFormat(style) if isinstance(style, QTextListFormat) else style)

    def _quote(self) -> None:
        cursor = self.edit.textCursor()
        cursor.beginEditBlock()
        block_fmt = cursor.blockFormat()
        block_fmt.setIndent(max(1, block_fmt.indent() + 1))
        cursor.setBlockFormat(block_fmt)
        cursor.endEditBlock()

    def _hr(self) -> None:
        cursor = self.edit.textCursor()
        cursor.insertHtml("<hr/>")
        cursor.insertBlock()

    def _link(self) -> None:
        cursor = self.edit.textCursor()
        default = cursor.selectedText() or ""
        url, ok = QInputDialog.getText(self, "Vložit odkaz", "URL:", text="https://")
        if not ok or not url:
            return
        text = default or url
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(url)
        fmt.setForeground(QColor(theme.current().accent))
        fmt.setFontUnderline(True)
        cursor.insertText(text, fmt)

    # ------------------------------------------------------------------
    # Přepínání zdroj / WYSIWYG
    # ------------------------------------------------------------------
    def _toggle_source(self, on: bool) -> None:
        if on:
            md = self.edit.toMarkdown()
            self.edit.blockSignals(True)
            self.edit.setAcceptRichText(False)
            self.edit.setPlainText(md)
            self.edit.setFontFamily("Consolas")
            self.edit.blockSignals(False)
        else:
            md = self.edit.toPlainText()
            self.edit.blockSignals(True)
            self.edit.setAcceptRichText(True)
            self.edit.document().setDefaultFont(self._doc_font())
            self.edit.setMarkdown(md)
            self.edit.blockSignals(False)
        self._source_mode = on
        for act in self._format_actions:
            act.setEnabled(not on)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    def set_markdown(self, text: str) -> None:
        if self.source_action.isChecked():
            self.source_action.setChecked(False)  # vrátí do WYSIWYG
        self.edit.blockSignals(True)
        self.edit.setAcceptRichText(True)
        self.edit.document().setDefaultFont(self._doc_font())
        self.edit.setMarkdown(text or "")
        self.edit.blockSignals(False)

    def to_markdown(self) -> str:
        if self._source_mode:
            return self.edit.toPlainText()
        return self.edit.toMarkdown()

    def clear(self) -> None:
        self.edit.blockSignals(True)
        self.edit.clear()
        self.edit.blockSignals(False)
