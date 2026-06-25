"""Task Master - spouštěč aplikace.

Spuštění (bez konzole na Windows): dvojklik na run.vbs nebo run.bat,
případně z příkazové řádky: pythonw main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

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


APP_STYLESHEET = """
QGroupBox {
    font-weight: 600;
    border: 1px solid #dcdcdc;
    border-radius: 6px;
    margin-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: #666;
}
QComboBox, QLineEdit, QSpinBox, QTextEdit {
    border: 1px solid #cfcfcf;
    border-radius: 4px;
    padding: 2px 4px;
    background: #ffffff;
}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QTextEdit:focus {
    border: 1px solid #4f7cff;
}
QPushButton {
    border: 1px solid #c9c9c9;
    border-radius: 4px;
    padding: 4px 10px;
    background: #f6f6f6;
}
QPushButton:hover { background: #eef2ff; border-color: #4f7cff; }
QToolBar { border: 0; spacing: 2px; padding: 2px; }
QTreeWidget { border: 1px solid #dcdcdc; border-radius: 6px; }
"""


def main() -> int:
    _set_windows_app_id()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)

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
