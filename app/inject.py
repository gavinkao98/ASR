"""文字注入：預設剪貼簿+Ctrl+V；備選逐字打字。貼完還原原剪貼簿文字。
限制：只備份/還原「文字」內容；原剪貼簿若是圖片等非文字格式，無法還原（記入 README）。"""
import time

import keyboard
import win32clipboard
import win32con

from app.logger import get_logger

log = get_logger("inject")

# 目標視窗在貼上的瞬間會獨佔開啟剪貼簿讀取內容；還原時多重試幾次撐過那段鎖定，避免把
# 使用者原本複製的東西洗掉（這正是「常常覆蓋掉之前複製內容」的成因）。OpenClipboard 是
# 獨佔的：一直重試到搶得到＝目標視窗已讀完，順序天然正確。最多 20 × 0.05 ≈ 1 秒。
_CLIP_RETRIES = 20
_CLIP_WAIT = 0.05


def _get_clipboard_text() -> str | None:
    for _ in range(_CLIP_RETRIES):  # 剪貼簿被其他程式短暫鎖定時重試
        try:
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                    return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                return None
            finally:
                win32clipboard.CloseClipboard()
        except Exception:  # noqa: BLE001
            time.sleep(_CLIP_WAIT)
    return None


def _set_clipboard_text(text: str) -> None:
    for _ in range(_CLIP_RETRIES):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
                return
            finally:
                win32clipboard.CloseClipboard()
        except Exception:  # noqa: BLE001
            time.sleep(_CLIP_WAIT)
    raise RuntimeError("無法寫入剪貼簿")


class ClipboardGuard:
    """備份進入時的剪貼簿文字，離開時還原；還原靠 _set_clipboard_text 的重試撐過目標視窗
    的短暫鎖定，確保原本複製的內容不會被辨識結果覆蓋。"""

    def __enter__(self):
        self._saved = _get_clipboard_text()
        return self

    def __exit__(self, *exc):
        if self._saved is not None:
            try:
                _set_clipboard_text(self._saved)
            except RuntimeError:
                log.warning("還原剪貼簿失敗")
        return False


def inject_text(text: str, mode: str = "clipboard") -> bool:
    """回傳是否成功送出（僅代表動作完成，無法保證目標視窗接受）。"""
    if not text:
        return False
    try:
        if mode == "type":
            keyboard.write(text, delay=0.002)
            return True
        with ClipboardGuard():
            _set_clipboard_text(text)
            time.sleep(0.05)           # 讓剪貼簿寫入落定
            keyboard.send("ctrl+v")
            time.sleep(0.2)            # 給目標視窗抓走內容的時間；離開時的還原會重試撐過鎖定
        return True
    except Exception:  # noqa: BLE001
        log.exception("inject failed")
        try:
            _set_clipboard_text(text)  # 失敗保底：至少把文字留在剪貼簿
        except RuntimeError:
            pass
        return False
