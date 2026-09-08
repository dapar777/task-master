"""Dialog nastavení e-mailové schránky pro načítání úkolů (IMAP)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from . import mailimport, theme
from .mailimport import MailSettings, MailWorker


class MailSettingsDialog(QDialog):
    """Server, přihlášení, složka a interval automatické kontroly.

    Tlačítko *Otestovat připojení* běží ve vlákně (síť nesmí zmrazit okno);
    výsledek se ukáže pod formulářem.
    """

    def __init__(self, settings: MailSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Načítání úkolů z e-mailu")
        self.setMinimumWidth(theme.px(460))
        self._worker: MailWorker | None = None

        self.host = QLineEdit(settings.host)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(settings.port))
        self.ssl = QCheckBox("SSL/TLS (port 993)")
        self.ssl.setChecked(bool(settings.ssl))
        self.user = QLineEdit(settings.user)
        self.password = QLineEdit(settings.password)
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.folder = QLineEdit(settings.folder or "INBOX")
        self.interval = QSpinBox()
        self.interval.setRange(0, 24 * 60)
        self.interval.setSuffix(" min")
        self.interval.setSpecialValueText("vypnuto")
        self.interval.setValue(int(settings.interval_min))

        form = QFormLayout()
        form.addRow("Server (IMAP):", self.host)
        port_row = QHBoxLayout()
        port_row.addWidget(self.port)
        port_row.addWidget(self.ssl)
        port_row.addStretch(1)
        form.addRow("Port:", port_row)
        form.addRow("Přihlašovací jméno:", self.user)
        form.addRow("Heslo:", self.password)
        form.addRow("Složka:", self.folder)
        form.addRow("Kontrolovat automaticky každých:", self.interval)

        hint = QLabel(
            "Každý nepřečtený e-mail se stane úkolem v sekci <b>_INBOX</b> "
            "(předmět = název, text i přílohy = obsah úkolu) a ve schránce se označí "
            "jako přečtený. Heslo se ukládá do Správce pověření Windows."
        )
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.TextFormat.RichText)

        self.test_btn = QPushButton("Otestovat připojení")
        self.test_btn.clicked.connect(self._test)
        self.result = QLabel("")
        self.result.setWordWrap(True)
        test_row = QHBoxLayout()
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.result, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(hint)
        lay.addLayout(form)
        lay.addLayout(test_row)
        lay.addWidget(buttons)

    def values(self) -> MailSettings:
        return MailSettings(
            host=self.host.text().strip(),
            port=int(self.port.value()),
            ssl=self.ssl.isChecked(),
            user=self.user.text().strip(),
            password=self.password.text(),
            folder=self.folder.text().strip() or "INBOX",
            interval_min=int(self.interval.value()),
        )

    def _test(self) -> None:
        if self._worker is not None:
            return
        vals = self.values()
        if not vals.complete:
            self.result.setText("Vyplň server, jméno a heslo.")
            return
        self.test_btn.setEnabled(False)
        self.result.setText("Připojuji…")
        w = MailWorker(mailimport.test_connection, vals, parent=self)
        w.done.connect(self._on_tested)
        w.finished.connect(w.deleteLater)
        self._worker = w
        w.start()

    def _on_tested(self, res, err) -> None:
        self._worker = None
        self.test_btn.setEnabled(True)
        self.result.setText(str(res) if err is None else f"Chyba: {err}")

    def reject(self) -> None:
        self._wait_worker()
        super().reject()

    def accept(self) -> None:
        self._wait_worker()
        super().accept()

    def _wait_worker(self) -> None:
        w = self._worker
        if w is not None and w.isRunning():
            w.wait(3000)

    @staticmethod
    def get(parent, settings: MailSettings) -> MailSettings | None:
        dlg = MailSettingsDialog(settings, parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.values()
        return None
