"""文字注入：預設剪貼簿+Ctrl+V（剪貼簿操作全委由常駐「替身」子行程），備選逐字輸入。

為什麼要替身：主行程內的 API 攔截層（防毒注入 DLL）會在 SetClipboardData 呼叫中
造成 heap 損毀（0xc0000374，crash dump×4＋faulthandler×4＋heapprobe 交叉定罪）。
剪貼簿讀寫全部移進拋棄式子行程（app/clipboard_helper.py）後，攔截層再出事死的是
替身——主行程收屍重生即可。替身常駐（冷啟含防毒掃描實測 ~0.8s，只在預熱時付一次）。

逐字輸入（type 模式/退路）用單批 SendInput：整句原子性進輸入佇列。注意中文輸入法
仍可能把注入字元抓進組字緩衝造成標點錯位（跨行程無解），故剪貼簿模式為預設。
"""
import base64
import ctypes
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

import keyboard

from app.logger import get_logger, log_dir

log = get_logger("inject")

# ---- 逐字輸入：單批 SendInput（VK_PACKET unicode）----
# keyboard.write 逐字慢送會與中文輸入法非同步處理交錯（標點錯位「，，。」擠團），
# 整句打包成一次 SendInput 可消除我方送入側的空隙，且長句即刻出字。
_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004
_VK_RETURN = 0x0D

_user32 = ctypes.windll.user32
_user32.SendInput.restype = wintypes.UINT
_user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t))


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = (("ki", _KEYBDINPUT), ("_pad", ctypes.c_ubyte * 32))

    _anonymous_ = ("u",)
    _fields_ = (("type", wintypes.DWORD), ("u", _U))


def _utf16_units(text: str) -> list[int]:
    """展開為 UTF-16 編碼單元（BMP 一單元；增補平面代理對兩單元，Windows 自行重組）。"""
    b = text.encode("utf-16-le")
    return [int.from_bytes(b[i:i + 2], "little") for i in range(0, len(b), 2)]


def _send_unicode_batch(units: list[int]) -> None:
    if not units:
        return
    n = len(units) * 2
    arr = (_INPUT * n)()
    for i, u in enumerate(units):
        down, up = arr[2 * i], arr[2 * i + 1]
        down.type = up.type = _INPUT_KEYBOARD
        down.ki.wScan = up.ki.wScan = u
        down.ki.dwFlags = _KEYEVENTF_UNICODE
        up.ki.dwFlags = _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP
    sent = _user32.SendInput(n, arr, ctypes.sizeof(_INPUT))
    if sent != n:
        raise RuntimeError(f"SendInput 僅送出 {sent}/{n} 個事件")


def _send_enter() -> None:
    arr = (_INPUT * 2)()
    arr[0].type = arr[1].type = _INPUT_KEYBOARD
    arr[0].ki.wVk = arr[1].ki.wVk = _VK_RETURN
    arr[1].ki.dwFlags = _KEYEVENTF_KEYUP
    _user32.SendInput(2, arr, ctypes.sizeof(_INPUT))


def _type_text(text: str) -> None:
    """逐字輸出整段文字：每段一批、換行送 Enter。"""
    for i, seg in enumerate(text.split("\n")):
        if i:
            _send_enter()
        if seg:
            _send_unicode_batch(_utf16_units(seg))


# ---- 剪貼簿替身編排 ----
_HELPER_PATH = Path(__file__).with_name("clipboard_helper.py")


def _multiformat_enabled() -> bool:
    """多格式（圖片/檔案/富文字）快照還原開關（config: clipboard_multiformat，預設開）。
    操作已隔離於替身行程，最壞情況＝該輪還原失敗記警告，主行程與貼上結果無損。"""
    try:
        from app import config
        return bool(config.load().get("clipboard_multiformat", True))
    except Exception:  # noqa: BLE001 - 設定讀不到就走最保守（仍可還原文字）
        return True


class _HelperClient:
    """常駐替身的生命週期與協議（READY/RESTORE/DONE）。僅由 pipeline 單一執行緒使用；
    任何異常一律收屍，下次使用自動重生。"""

    def __init__(self):
        self._proc: subprocess.Popen | None = None

    def _ensure(self) -> bool:
        if self._proc is not None and self._proc.poll() is None:
            return True
        try:
            logf = (log_dir() / "cliphelper.log").open("ab")
            try:
                self._proc = subprocess.Popen(
                    [sys.executable, "-S", "-E", str(_HELPER_PATH)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=logf,
                    creationflags=subprocess.CREATE_NO_WINDOW)
            finally:
                logf.close()  # 子行程已繼承 handle
            return True
        except Exception:  # noqa: BLE001
            log.exception("剪貼簿替身啟動失敗")
            self._proc = None
            return False

    def _read_line(self, timeout: float) -> bytes | None:
        proc = self._proc
        box: list[bytes] = []
        t = threading.Thread(target=lambda: box.append(proc.stdout.readline()),
                             daemon=True)
        t.start()
        t.join(timeout)
        return box[0].strip() if box else None

    def kill(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
            except Exception:  # noqa: BLE001
                pass
            self._proc = None

    def begin(self, text: str, multiformat: bool) -> bool:
        """替身快照原剪貼簿＋寫入新文字；True＝可送 Ctrl+V。失敗自動收屍。"""
        if not self._ensure():
            return False
        try:
            flag = b"1" if multiformat else b"0"
            payload = base64.b64encode(text.encode("utf-8"))
            self._proc.stdin.write(flag + b" " + payload + b"\n")
            self._proc.stdin.flush()
            if self._read_line(3.0) == b"READY":
                return True
            log.warning("替身未回 READY（逾時或暴斃）")
        except Exception:  # noqa: BLE001
            log.exception("替身通訊失敗")
        self.kill()
        return False

    def finish(self) -> None:
        """貼上完成後請替身還原原剪貼簿；失敗僅記警告（貼上已完成、不影響結果）。"""
        if self._proc is None:
            return
        try:
            self._proc.stdin.write(b"RESTORE\n")
            self._proc.stdin.flush()
            if self._read_line(3.0) != b"DONE":
                log.warning("替身還原逾時/失敗（貼上不受影響）")
                self.kill()
        except Exception:  # noqa: BLE001
            log.warning("替身還原通訊失敗（貼上不受影響）", exc_info=True)
            self.kill()


_helper = _HelperClient()


def warm_clipboard_helper() -> None:
    """App 啟動時預熱替身：冷啟（含防毒掃描）實測 ~0.8 秒，先在背景付掉。"""
    threading.Thread(target=_helper._ensure, daemon=True).start()


def inject_text(text: str, mode: str = "clipboard") -> bool:
    """回傳是否成功送出（僅代表動作完成，無法保證目標視窗接受）。"""
    if not text:
        return False
    try:
        if mode == "type":
            _type_text(text)
            return True
        from app.heapprobe import checkpoint  # 0xc0000374 觀察期探針
        if _helper.begin(text, _multiformat_enabled()):
            checkpoint("替身備妥後")
            keyboard.send("ctrl+v")
            time.sleep(0.2)   # 給目標視窗抓走內容的時間
            _helper.finish()
            checkpoint("替身還原後")
        else:
            # 替身不可用：逐字輸出，文字一樣送達（標點可能受輸入法影響，聊勝於失敗）
            log.warning("剪貼簿替身不可用，改逐字輸出")
            _type_text(text)
        return True
    except Exception:  # noqa: BLE001
        log.exception("inject failed")
        # 收掉可能卡在等 RESTORE 的替身：其 EOF 語意會把辨識文字留在剪貼簿，
        # 保留「手動 Ctrl+V」退路（等同舊版失敗保底）。
        _helper.kill()
        return False
