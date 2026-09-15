"""Task Master - spouštěč aplikace.

Spuštění (bez konzole na Windows): dvojklik na run.vbs nebo run.bat,
případně z příkazové řádky: pythonw main.py

Bez konzole (pythonw) by neošetřená výjimka zmizela beze stopy – aplikace
by se „nespustila“. Proto je tu `sys.excepthook`, který pád zapíše do
`crash.log` v adresáři konfigurace a ukáže dialog s chybou.
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtWidgets import QApplication, QMessageBox

from app import theme
from app.appicon import app_icon, claim_process_identity
from app.constants import APP_NAME, ORG_NAME
from app.mainwindow import MainWindow


def crash_log_path() -> Path:
    """`crash.log` vedle shortcuts.json (adresář konfigurace aplikace)."""
    d = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation))
    d.mkdir(parents=True, exist_ok=True)
    return d / "crash.log"


def excepthook(exc_type, exc, tb) -> None:
    """Neošetřená výjimka (start i sloty za běhu): log + dialog, ne tiché zmizení."""
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    where = ""
    try:
        path = crash_log_path()
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} ===\n{text}")
        where = f"\n\nPodrobnosti: {path}"
    except OSError:
        pass
    sys.__excepthook__(exc_type, exc, tb)  # do konzole, když nějaká je
    if QApplication.instance() is not None:
        QMessageBox.critical(None, f"{APP_NAME} – chyba",
                             f"Neočekávaná chyba:\n{exc_type.__name__}: {exc}{where}")


def main() -> int:
    sys.excepthook = excepthook
    # vlastní identita procesu v hlavním panelu (jinak ikona Pythonu)
    claim_process_identity()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    # vzhled (Solarized světlé/tmavé) a zoom UI – jediný zdroj barev je app/theme.py
    settings = QSettings(ORG_NAME, APP_NAME)
    theme_name = settings.value("theme", "light", type=str)
    theme.apply(app, theme_name, zoom=settings.value("zoom", 1.0, type=float))

    # ikona ze sady Terakota (assets/icons), varianta podle tématu;
    # okno si ji při zobrazení a změně tématu prosadí i v hlavním panelu
    app.setWindowIcon(app_icon(theme_name))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
