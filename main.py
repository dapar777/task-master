"""Task Master - spouštěč aplikace.

Spuštění (bez konzole na Windows): dvojklik na run.vbs nebo run.bat,
případně z příkazové řádky: pythonw main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app import theme
from app.appicon import make_app_icon, save_icon_files
from app.constants import APP_NAME, ORG_NAME
from app.mainwindow import MainWindow


def _set_windows_app_id() -> None:
    """Aby Windows v hlavním panelu použil naši ikonu místo ikony Pythonu."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        func = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        func.argtypes = [ctypes.c_wchar_p]  # widestring marshaling
        func.restype = ctypes.c_long
        func("TaskMaster.App.1")
    except Exception:
        pass


def main() -> int:
    _set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    # vzhled (Solarized světlé/tmavé) – jediný zdroj barev je app/theme.py
    theme.apply(app, QSettings(ORG_NAME, APP_NAME).value("theme", "light", type=str))

    icon = make_app_icon()
    app.setWindowIcon(icon)
    # ulož PNG/ICO vedle aplikace (pro zástupce na ploše)
    save_icon_files(Path(__file__).resolve().parent / "assets")

    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
