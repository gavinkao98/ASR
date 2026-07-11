"""HKCU Run 開機自啟（免管理員）。啟動指令＝pythonw main.py。"""
import sys
import winreg

from app.paths import ROOT

APP_KEY_NAME = "ASRVoiceTyping"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command() -> str:
    pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    return f'"{pythonw}" "{ROOT / "main.py"}"'


def set_autostart(enabled: bool) -> None:
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE)
    with key:
        if enabled:
            winreg.SetValueEx(key, APP_KEY_NAME, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(key, APP_KEY_NAME)
            except FileNotFoundError:
                pass


def is_enabled() -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ)
        with key:
            winreg.QueryValueEx(key, APP_KEY_NAME)
            return True
    except FileNotFoundError:
        return False
