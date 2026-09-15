"""Jedno okno nastavení aplikace.

Sekce vlevo, stránka vpravo (stejný vzor jako správa uložených filtrů).
Dialog nic neaplikuje sám – jen sbírá hodnoty; po *Uložit* je promítne
`MainWindow._apply_settings`, které drží v synchronu menu, hlavičku,
QSettings i běžící časovače. Výjimkou jsou zkratky: `ShortcutEditor` má
vlastní kontrolu kolizí a ukládá se sám.

Totéž, co je tady, jde přepínat i z příkazové palety (kategorie
*Nastavení*), takže se hodnoty nemají číst z widgetů dialogu, ale vždy
z okna / `theme` / QSettings – dialog je jen jeden z pohledů na ně.

Hledání (pole nad sekcemi, Ctrl+F): každý řádek formuláře je v indexu
(`_index_form`, popisek + tooltip + klíčová slova); dotaz se vyhodnotí
stejně jako hledání úkolů (`search.parse`: víc slov = všechna, bez
diakritiky). Sekce bez nálezu z levého seznamu zmizí, nalezené řádky se
zvýrazní vlastností `searchHit` (QSS v `theme.py`), v sekci Zkratky se
filtruje strom příkazů. Nový řádek v dialogu = nový záznam v indexu.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import icons, search, theme
from .constants import SNOOZE_MAX_DAYS
from .maildialog import MailSettingsForm
from .shortcutdialog import ShortcutEditor
from .taskdialog import format_duration
from .widgets import HLine, SectionLabel, SegmentedControl

#: (klíč, popisek v seznamu, ikona) – pořadí = pořadí v levém seznamu
SECTIONS = (
    ("appearance", "Vzhled", "sun"),
    ("workspace", "Prostor", "folder"),
    ("snooze", "Odklad", "clock"),
    ("mail", "E-mail", "mail"),
    ("shortcuts", "Zkratky", "keyboard"),
    ("other", "Ostatní", "sliders"),
)

#: hodnoty zoomu nabízené posuvníkem (v %), stejné jako v paletě
ZOOM_MIN_PCT = int(round(theme.ZOOM_MIN * 100))
ZOOM_MAX_PCT = int(round(theme.ZOOM_MAX * 100))

_TAG_RE = re.compile(r"<[^>]+>")


def _plain(text: str) -> str:
    """Text popisku bez HTML značek (poznámky jsou RichText)."""
    return _TAG_RE.sub(" ", text or "").replace("&", "")


class SettingsDialog(QDialog):
    """Nastavení: vzhled, prostor, odklad, e-mail, zkratky, ostatní."""

    def __init__(self, win, section: str | None = None, parent=None):
        super().__init__(parent or win)
        self.win = win
        self.setWindowTitle("Nastavení")
        self.resize(theme.px(780), theme.px(580))
        self.setMinimumSize(theme.px(620), theme.px(440))
        self._workspace_path: Path | None = (
            Path(win.workspace.root) if getattr(win, "workspace", None) else None
        )

        # --- hlavička
        heading = QLabel("Nastavení")
        heading.setFont(theme.title_font(14))
        sub = QLabel("Změny se použijí tlačítkem Uložit. Téma, zoom, odklad i kontrolu "
                     "e-mailu lze přepínat také z příkazové palety (Ctrl+Shift+P → Nastavení).")
        sub.setObjectName("hint")
        sub.setWordWrap(True)

        # --- hledání: index řádků (sekce, text, widgety) plní _index_form;
        # text sekce (název + nadpis + vysvětlení) je kontext každého jejího řádku
        self._entries: list[tuple[str, str, list[QWidget]]] = []
        self._section_text: dict[str, str] = {}
        self._hits: list[QWidget] = []
        self.search = QLineEdit()
        self.search.setObjectName("settingsSearch")
        self.search.setPlaceholderText("Hledat v nastavení…  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icons.icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setToolTip("Víc slov musí sedět všechna; diakritika ani velikost písmen nerozhodují.\n"
                               "Esc vyčistí, Enter skočí na první nález.")
        self.search.textChanged.connect(self._apply_search)
        self.search.installEventFilter(self)  # Enter / Esc, viz eventFilter
        self.search_status = QLabel("")
        self.search_status.setObjectName("hint")
        self.search_status.setWordWrap(True)
        QShortcut(QKeySequence.StandardKey.Find, self, activated=self._focus_search)

        # --- sekce vlevo, stránky vpravo
        self.nav = QListWidget()
        self.nav.setObjectName("settingsNav")
        self.nav.setFixedWidth(theme.px(190))
        self.nav.setIconSize(QSize(theme.px(16), theme.px(16)))
        self.nav.setSpacing(theme.px(2))
        self.nav.setFrameShape(QFrame.Shape.NoFrame)
        self.stack = QStackedWidget()
        self._pages: dict[str, int] = {}

        self._build_appearance()
        self._build_workspace()
        self._build_snooze()
        self._build_mail()
        self._build_shortcuts()
        self._build_other()

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)

        side = QVBoxLayout()
        side.setSpacing(theme.px(6))
        side.addWidget(self.search)
        side.addWidget(self.search_status)
        side.addWidget(self.nav, 1)
        self.search.setFixedWidth(theme.px(190))
        self.search_status.setFixedWidth(theme.px(190))

        body = QHBoxLayout()
        body.setSpacing(theme.px(14))
        body.addLayout(side)
        body.addWidget(self.stack, 1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Uložit")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Zrušit")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(theme.px(10))
        lay.addWidget(heading)
        lay.addWidget(sub)
        lay.addWidget(HLine())
        lay.addLayout(body, 1)
        lay.addWidget(self.buttons)

        self.select_section(section or SECTIONS[0][0])
        self.search.setFocus()

    # ------------------------------------------------------------------
    # stavba stránek
    # ------------------------------------------------------------------
    def _add_page(self, key: str, title: str, hint: str, body: QWidget) -> None:
        """Stránka = nadpis + vysvětlení + obsah (v rolovací oblasti)."""
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(theme.px(8))
        h = QLabel(title)
        h.setFont(theme.title_font(12))
        pl.addWidget(h)
        if hint:
            hl = QLabel(hint)
            hl.setObjectName("hint")
            hl.setWordWrap(True)
            pl.addWidget(hl)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        pl.addWidget(scroll, 1)

        label, icon_name = next((lbl, ic) for k, lbl, ic in SECTIONS if k == key)
        item = QListWidgetItem(icons.icon(icon_name, theme.px(16)), label)
        item.setData(Qt.ItemDataRole.UserRole, key)
        self.nav.addItem(item)
        self._pages[key] = self.stack.addWidget(page)
        # název sekce, nadpis a vysvětlení hledání najde bez zvýraznění řádku
        self._section_text[key] = f"{label} {title} {hint}"

    def _index_form(self, key: str, form: QFormLayout, keywords: dict[str, str] | None = None) -> None:
        """Zařadí řádky formuláře do hledání: popisek + text/tooltip/placeholder
        polí + volitelná klíčová slova (podle popisku řádku)."""
        keywords = keywords or {}
        for row in range(form.rowCount()):
            widgets: list[QWidget] = []
            texts: list[str] = []
            for role in (QFormLayout.ItemRole.LabelRole, QFormLayout.ItemRole.FieldRole):
                item = form.itemAt(row, role)
                if item is None:
                    continue
                if item.widget() is not None:
                    widgets.append(item.widget())
                elif item.layout() is not None:
                    lay = item.layout()
                    widgets.extend(w for w in (lay.itemAt(i).widget() for i in range(lay.count())) if w)
            label_text = ""
            for w in widgets:
                for attr in ("text", "placeholderText", "toolTip"):
                    fn = getattr(w, attr, None)
                    val = fn() if callable(fn) else ""
                    if isinstance(val, str) and val:
                        texts.append(_plain(val))
                if isinstance(w, QLabel) and not label_text:
                    label_text = w.text()
            texts.append(keywords.get(label_text, ""))
            self._entries.append((key, " ".join(texts), widgets))

    def _build_appearance(self) -> None:
        win = self.win
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        # téma
        self.theme_seg = SegmentedControl()
        self.theme_seg.add("light", "Světlé", "sun")
        self.theme_seg.add("dark", "Tmavé", "moon")
        self.theme_seg.set_current("dark" if theme.is_dark() else "light")
        form.addRow("Téma:", self.theme_seg)

        # zoom
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(ZOOM_MIN_PCT, ZOOM_MAX_PCT)
        self.zoom_slider.setSingleStep(10)
        self.zoom_slider.setPageStep(10)
        self.zoom_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.zoom_slider.setTickInterval(10)
        self.zoom_slider.setValue(int(round(theme.zoom() * 100)))
        self.zoom_value = QLabel()
        self.zoom_value.setMinimumWidth(theme.px(48))
        self.zoom_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        zoom_reset = QPushButton("100 %")
        zoom_reset.setToolTip("Původní velikost")
        zoom_reset.clicked.connect(lambda: self.zoom_slider.setValue(100))
        self.zoom_slider.valueChanged.connect(self._sync_zoom_label)
        self._sync_zoom_label(self.zoom_slider.value())
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(self.zoom_slider, 1)
        zoom_row.addWidget(self.zoom_value)
        zoom_row.addWidget(zoom_reset)
        form.addRow("Zoom celého UI:", zoom_row)
        zoom_hint = QLabel("Za běhu i Ctrl+kolečko, Ctrl++ / Ctrl+-, Ctrl+0 = 100 %.")
        zoom_hint.setObjectName("hint")
        zoom_hint.setWordWrap(True)
        form.addRow("", zoom_hint)

        # karty
        self.compact_check = QCheckBox("Úsporné karty v Bez rušení")
        self.compact_check.setToolTip("Úkoly mimo Probíhá / Ke zpracování (a doběhlé odklady) jsou nižší")
        self.compact_check.setChecked(bool(getattr(win, "_compact_cards", True)))
        form.addRow("Karty:", self.compact_check)

        self._add_page("appearance", "Vzhled",
                       "Barvy má na starosti jediné místo (Solarized, světlé i tmavé); "
                       "zoom zvětšuje písma, ikony i rozměry najednou.", body)
        self._index_form("appearance", form, {
            "Téma:": "světlé tmavé barvy noční režim",
            "Zoom celého UI:": "velikost písma měřítko zvětšit zmenšit lupa",
            "Karty:": "bez rušení úsporné kompaktní karty",
        })

    def _sync_zoom_label(self, value: int) -> None:
        self.zoom_value.setText(f"{int(value)} %")

    def _build_workspace(self) -> None:
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self.workspace_edit = QLineEdit(str(self._workspace_path or ""))
        self.workspace_edit.setReadOnly(True)
        change_btn = QPushButton("Změnit…")
        change_btn.clicked.connect(self._choose_workspace)
        open_btn = QPushButton("Otevřít v Průzkumníku")
        open_btn.clicked.connect(self._open_workspace_folder)
        row = QHBoxLayout()
        row.addWidget(self.workspace_edit, 1)
        row.addWidget(change_btn)
        row.addWidget(open_btn)
        form.addRow("Pracovní prostor:", row)

        note = QLabel(
            "Prostor je obyčejná složka: každý úkol je podsložka s <code>.md</code> a "
            "<code>.yaml</code>. Stav zobrazení, filtr a historie hledání se ukládají do "
            "<code>_state.yaml</code> uvnitř prostoru – sdílí se tedy i s Androidem, "
            "když oba pracují nad stejnou složkou."
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        note.setTextFormat(Qt.TextFormat.RichText)
        form.addRow("", note)

        self._add_page("workspace", "Pracovní prostor",
                       "Změna prostoru se provede po uložení; rozpracovaný popis úkolu se nejdřív uloží.",
                       body)
        self._index_form("workspace", form, {
            "Pracovní prostor:": "složka adresář cesta otevřít workspace",
        })

    def _choose_workspace(self) -> None:
        start = str(self._workspace_path) if self._workspace_path else ""
        chosen = QFileDialog.getExistingDirectory(self, "Vyber pracovní prostor", start)
        if chosen:
            self._workspace_path = Path(chosen)
            self.workspace_edit.setText(chosen)

    def _open_workspace_folder(self) -> None:
        if self._workspace_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._workspace_path)))

    def _build_snooze(self) -> None:
        win = self.win
        d, h, m = getattr(win, "_last_snooze", (0, 0, 10))
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self.snooze_days = QSpinBox()
        self.snooze_days.setRange(0, SNOOZE_MAX_DAYS)
        self.snooze_days.setSuffix(" d")
        self.snooze_hours = QSpinBox()
        self.snooze_hours.setRange(0, 23)
        self.snooze_hours.setSuffix(" h")
        self.snooze_minutes = QSpinBox()
        self.snooze_minutes.setRange(0, 59)
        self.snooze_minutes.setSuffix(" min")
        for box, val in ((self.snooze_days, d), (self.snooze_hours, h), (self.snooze_minutes, m)):
            box.setValue(int(val))
            box.valueChanged.connect(self._sync_snooze_summary)
        row = QHBoxLayout()
        row.addWidget(self.snooze_days)
        row.addWidget(self.snooze_hours)
        row.addWidget(self.snooze_minutes)
        row.addStretch(1)
        form.addRow("Výchozí interval:", row)
        self.snooze_summary = QLabel()
        self.snooze_summary.setObjectName("hint")
        form.addRow("", self.snooze_summary)
        self._sync_snooze_summary()

        self._add_page("snooze", "Odklad („Čeká do…“)",
                       "Interval, který dialog odkladu předvyplní. Každé použití dialogu "
                       "ho přepíše naposledy zvolenou hodnotou; předvolby jsou i v paletě "
                       "(Úkol › Odložit o).", body)
        self._index_form("snooze", form, {
            "Výchozí interval:": "odložit odklad čekat do dny hodiny minuty odpočet",
        })

    def snooze_parts(self) -> tuple[int, int, int]:
        return (int(self.snooze_days.value()), int(self.snooze_hours.value()),
                int(self.snooze_minutes.value()))

    def _sync_snooze_summary(self, *_a) -> None:
        d, h, m = self.snooze_parts()
        secs = d * 86400 + h * 3600 + m * 60
        self.snooze_summary.setText(
            "Nastav aspoň minutu – nulový interval se nepamatuje." if secs <= 0
            else f"Dialog Čekat do… předvyplní: {format_duration(secs)}"
        )

    def _build_mail(self) -> None:
        self.mail_form = MailSettingsForm(self.win.mail_settings)
        self._add_page("mail", "Úkoly z e-mailu",
                       "Nepřečtené zprávy ze schránky (IMAP) se stanou úkoly v sekci _INBOX. "
                       "Ruční načtení: Ctrl+Shift+M.", self.mail_form)
        self._index_form("mail", self.mail_form.form_layout, {
            "Server (IMAP):": "e-mail mail schránka pošta seznam",
            "Port:": "ssl tls zabezpečení",
            "Přihlašovací jméno:": "účet uživatel login e-mail",
            "Heslo:": "správce pověření",
            "Složka:": "inbox",
            "Kontrolovat automaticky každých:": "interval kontrola automaticky stahování minuty",
        })
        self._entries.append(("mail", "otestovat připojení test", [self.mail_form.test_btn]))

    def _build_shortcuts(self) -> None:
        self.shortcut_editor = ShortcutEditor(self.win.shortcuts)
        self._add_page("shortcuts", "Klávesové zkratky",
                       "Zkratky se ukládají zvlášť (shortcuts.json) a platí hned po uložení.",
                       self.shortcut_editor)
        # příkazy se nehledají přes index, ale filtrem stromu (_apply_search)

    def _build_other(self) -> None:
        win = self.win
        body = QWidget()
        vl = QVBoxLayout(body)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(theme.px(8))

        vl.addWidget(SectionLabel("Údržba"))
        self.clear_recent_check = QCheckBox("Vymazat „naposledy použité“ v příkazové paletě")
        self.reset_geometry_check = QCheckBox("Zapomenout polohu a velikost okna (příští start = výchozí)")
        vl.addWidget(self.clear_recent_check)
        vl.addWidget(self.reset_geometry_check)

        vl.addSpacing(theme.px(6))
        vl.addWidget(SectionLabel("Kde se nastavení ukládá"))
        cfg_dir = ""
        try:
            cfg_dir = str(Path(win.shortcuts.config_path).parent)
        except Exception:  # noqa: BLE001
            pass
        reg = ""
        try:
            reg = str(win.settings.fileName())
        except Exception:  # noqa: BLE001
            pass
        where = QLabel(
            f"Vzhled, prostor, odklad, e-mail (bez hesla): {reg or 'nastavení aplikace'}<br>"
            f"Zkratky a uložené filtry: {cfg_dir or 'adresář konfigurace aplikace'}<br>"
            "Heslo k e-mailu: Správce pověření Windows (položka TaskMaster/mail)<br>"
            "Stav zobrazení, filtr a historie hledání: <code>_state.yaml</code> v prostoru"
        )
        where.setObjectName("hint")
        where.setWordWrap(True)
        where.setTextFormat(Qt.TextFormat.RichText)
        where.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        vl.addWidget(where)
        vl.addStretch(1)

        self._add_page("other", "Ostatní", "", body)
        self._entries.append(("other", "údržba paleta naposledy použité historie vymazat "
                              + self.clear_recent_check.text(), [self.clear_recent_check]))
        self._entries.append(("other", "údržba okno geometrie poloha velikost výchozí "
                              + self.reset_geometry_check.text(), [self.reset_geometry_check]))
        self._entries.append(("other", "kde se ukládá soubory cesty registry nastavení " + _plain(where.text()),
                              [where]))

    # ------------------------------------------------------------------
    # hledání
    # ------------------------------------------------------------------
    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    @staticmethod
    def _mark(w: QWidget, hit: bool) -> None:
        if bool(w.property("searchHit")) == hit:
            return
        w.setProperty("searchHit", hit)
        w.style().unpolish(w)
        w.style().polish(w)

    def _row_hit(self, q, key: str, entry_text: str) -> bool:
        """Řádek sedí, když každé slovo dotazu je v řádku nebo v textu jeho
        sekce a aspoň jedno přímo v řádku („kontrola mail“ → interval v sekci
        E-mail, ale samotné „mail“ nezvýrazní celou sekci). Vzor se hledá jen
        v řádku."""
        if q.regex is not None or not q.words:
            return q.matches(entry_text)
        row = search.fold(entry_text)
        if not any(w in row for w in q.words):
            return False
        ctx = row + " " + search.fold(self._section_text.get(key, ""))
        return all(w in ctx for w in q.words)

    def _apply_search(self, text: str) -> None:
        """Skryje sekce bez nálezu, zvýrazní nalezené řádky, přepne na první
        sekci s nálezem. Prázdný dotaz vrátí vše."""
        q = search.parse(text)
        for w in self._hits:
            self._mark(w, False)
        self._hits = []
        hit_sections: set[str] = set()
        if not q.empty:
            for key, sec_text in self._section_text.items():
                if q.matches(sec_text):
                    hit_sections.add(key)
            for key, entry_text, widgets in self._entries:
                if self._row_hit(q, key, entry_text):
                    hit_sections.add(key)
                    self._hits.extend(widgets)
        for w in self._hits:
            self._mark(w, True)
        # strom příkazů má vlastní filtr; nález = sekce Zkratky
        if self.shortcut_editor.filter_rows(q) and not q.empty:
            hit_sections.add("shortcuts")

        nothing = not q.empty and not hit_sections
        for i in range(self.nav.count()):
            item = self.nav.item(i)
            key = str(item.data(Qt.ItemDataRole.UserRole))
            item.setHidden(bool(hit_sections) and key not in hit_sections)
        if q.empty:
            self.search_status.setText("")
        elif nothing:
            self.search_status.setText("Nic nenalezeno.")
        else:
            n = len(hit_sections)
            self.search_status.setText(f"{n} {'sekce' if n < 5 else 'sekcí'} s nálezem.")
        if hit_sections and self.current_section() not in hit_sections:
            first = next(k for k, _, _ in SECTIONS if k in hit_sections)
            self.select_section(first)

    def _focus_first_hit(self) -> None:
        """Enter v hledání: fokus na první nalezený ovládací prvek aktuální sekce."""
        page = self.stack.currentWidget()
        for w in self._hits:
            if (page is not None and page.isAncestorOf(w) and not isinstance(w, QLabel)
                    and w.focusPolicy() != Qt.FocusPolicy.NoFocus):
                w.setFocus()
                return

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        # Klávesy v hledacím poli se nesmí dostat k dialogu: Enter by stiskl
        # výchozí tlačítko Uložit (QLineEdit ho neakceptuje), Esc by dialog
        # zavřel. Enter = skok na první nález, Esc s textem = vyčistit.
        if obj is self.search and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._focus_first_hit()
                return True
            if event.key() == Qt.Key.Key_Escape and self.search.text():
                self.search.clear()
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    def select_section(self, key: str) -> None:
        idx = self._pages.get(key, 0)
        self.nav.setCurrentRow(idx)
        self.stack.setCurrentIndex(idx)

    def current_section(self) -> str:
        item = self.nav.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else SECTIONS[0][0]

    def values(self) -> dict:
        """Hodnoty z formuláře; aplikuje `MainWindow._apply_settings`."""
        return {
            "theme": self.theme_seg.current() or "light",
            "zoom": self.zoom_slider.value() / 100.0,
            "compact_cards": self.compact_check.isChecked(),
            "snooze": self.snooze_parts(),
            "mail": self.mail_form.values(),
            "workspace": self._workspace_path,
            "clear_palette_recent": self.clear_recent_check.isChecked(),
            "reset_geometry": self.reset_geometry_check.isChecked(),
        }

    def accept(self) -> None:
        self.mail_form.wait_worker()
        # zkratky mají vlastní uložení (kolize) – odmítnutá kolize dialog nezavře
        if self.shortcut_editor.is_dirty():
            self.select_section("shortcuts")
            if not self.shortcut_editor.save():
                return
        super().accept()

    def reject(self) -> None:
        self.mail_form.wait_worker()
        super().reject()

    @staticmethod
    def get(win, section: str | None = None) -> dict | None:
        """Otevře dialog; vrátí hodnoty po Uložit, jinak None."""
        dlg = SettingsDialog(win, section)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.values()
        return None
