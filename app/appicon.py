"""Ikona aplikace ze sady Terakota (assets/icons) a její prosazení v hlavním panelu.

Ikona je terakotový disk s prstencem bez pozadí (viz c:/code/terakota-icons);
tmavá varianta má krémový prstenec (na tmavé téma), světlá espresso (na světlé).

Windows a Python z Microsoft Store (MSIX): hlavní panel u balíčkovaných
procesů ukazuje logo *balíčku* (Python) a ikonu okna ignoruje. Samotné
SetCurrentProcessExplicitAppUserModelID nestačí – je třeba nastavit
AppUserModel vlastnosti přímo na HWND okna (pywin32 propsys): id, název,
ikona a příkaz pro znovuspuštění. Bez pywin32 se krok tiše přeskočí.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
APP_USER_MODEL_ID = "TaskMaster.App.2"


def icon_path(variant: str = "dark") -> Path:
    variant = "light" if variant == "light" else "dark"
    return ASSETS_DIR / f"task-master-{variant}.ico"


def app_icon(variant: str = "dark") -> QIcon:
    """QIcon pro dané téma („light" / „dark"); .ico (16–256 px) + PNG 512 px."""
    variant = "light" if variant == "light" else "dark"
    ico = icon_path(variant)
    png = ASSETS_DIR / f"task-master-{variant}-512.png"
    icon = QIcon(str(ico)) if ico.exists() else QIcon()
    if png.exists():
        icon.addFile(str(png))
    return icon


def make_app_icon() -> QIcon:
    """Ikona pro aktuální téma (zpětně kompatibilní název)."""
    from . import theme

    return app_icon("dark" if theme.is_dark() else "light")


def claim_process_identity() -> None:
    """Před vytvořením QApplication: vlastní AppUserModelID procesu, aby Windows
    okno neseskupoval pod python.exe."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        func = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        func.argtypes = [ctypes.c_wchar_p]
        func.restype = ctypes.c_long
        func(APP_USER_MODEL_ID)
    except Exception:
        pass


def apply_taskbar_identity(window, variant: str) -> bool:
    """Nastaví AppUserModel vlastnosti na HWND zobrazeného okna (Windows).

    Volat po show() a znovu při změně tématu (jiná varianta ikony).
    Vrací True, když se vlastnosti podařilo zapsat.
    """
    if sys.platform != "win32" or not window.isVisible():
        return False
    try:
        from win32com.propsys import propsys, pscon
    except Exception:
        return False
    ico = icon_path(variant)
    try:
        ps = propsys.SHGetPropertyStoreForWindow(int(window.winId()))
        ps.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(APP_USER_MODEL_ID))
        ps.SetValue(pscon.PKEY_AppUserModel_RelaunchDisplayNameResource,
                    propsys.PROPVARIANTType("Task Master"))
        if ico.exists():
            ps.SetValue(pscon.PKEY_AppUserModel_RelaunchIconResource,
                        propsys.PROPVARIANTType(f"{ico},0"))
        pyw = Path(sys.executable).with_name("pythonw.exe")
        exe = pyw if pyw.exists() else Path(sys.executable)
        main_py = ASSETS_DIR.parent.parent / "main.py"
        ps.SetValue(pscon.PKEY_AppUserModel_RelaunchCommand,
                    propsys.PROPVARIANTType(f'"{exe}" "{main_py}"'))
        ps.Commit()
        return True
    except Exception:
        return False  # kosmetika – nikdy neblokovat start
