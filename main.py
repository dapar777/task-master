"""Task Master - spouštěč aplikace.

Spuštění (bez konzole na Windows): dvojklik na run.vbs nebo run.bat,
případně z příkazové řádky: pythonw main.py
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app import theme
from app.appicon import app_icon, claim_process_identity
from app.constants import APP_NAME, ORG_NAME
from app.mainwindow import MainWindow


def main() -> int:
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
