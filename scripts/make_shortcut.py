"""在桌面建「語音輸入」捷徑指向 啟動語音輸入.vbs。"""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from pathlib import Path

import win32com.client

from app.paths import ROOT

if __name__ == "__main__":
    shell = win32com.client.Dispatch("WScript.Shell")
    desktop = Path(shell.SpecialFolders("Desktop"))
    sc = shell.CreateShortCut(str(desktop / "語音輸入.lnk"))
    sc.Targetpath = str(ROOT / "啟動語音輸入.vbs")
    sc.WorkingDirectory = str(ROOT)
    sc.save()
    print("桌面捷徑已建立")
