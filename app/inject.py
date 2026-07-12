"""文字注入：預設剪貼簿+Ctrl+V；備選逐字打字。貼完還原原剪貼簿文字。
限制：只備份/還原「文字」內容；原剪貼簿若是圖片等非文字格式，無法還原（記入 README）。"""
import ctypes
import time
from ctypes import wintypes

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

# ---- Win32 全域記憶體原始位元組讀寫（多格式備份的底層）----
_kernel32 = ctypes.windll.kernel32
_user32 = ctypes.windll.user32
_kernel32.GlobalSize.restype = ctypes.c_size_t
_kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalLock.restype = wintypes.LPVOID
_kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalUnlock.restype = wintypes.BOOL
_kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalFree.restype = wintypes.HGLOBAL
_kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
_user32.GetClipboardData.restype = wintypes.HANDLE
_user32.GetClipboardData.argtypes = [wintypes.UINT]
_user32.SetClipboardData.restype = wintypes.HANDLE
_user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_GMEM_MOVEABLE = 0x0002


def _read_format_bytes(fmt: int) -> bytes | None:
    """讀出剪貼簿上某格式的整塊原始位元組。呼叫前剪貼簿必須已 Open。
    非 HGLOBAL 格式或空資料回 None（白名單外的格式不會走到這裡）。"""
    h = _user32.GetClipboardData(fmt)
    if not h:
        return None
    size = _kernel32.GlobalSize(h)
    if not size:
        return None
    ptr = _kernel32.GlobalLock(h)
    if not ptr:
        return None
    try:
        return ctypes.string_at(ptr, size)
    finally:
        _kernel32.GlobalUnlock(h)


def _write_format_bytes(fmt: int, data: bytes) -> None:
    """把位元組原樣放回剪貼簿某格式。呼叫前剪貼簿必須已 Open。
    SetClipboardData 成功後記憶體歸系統所有；失敗才由我們 GlobalFree。"""
    h = _kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
    if not h:
        raise MemoryError("GlobalAlloc failed")
    ptr = _kernel32.GlobalLock(h)
    if not ptr:
        _kernel32.GlobalFree(h)
        raise MemoryError("GlobalLock failed")
    ctypes.memmove(ptr, data, len(data))
    _kernel32.GlobalUnlock(h)
    if not _user32.SetClipboardData(fmt, h):
        _kernel32.GlobalFree(h)
        raise RuntimeError(f"SetClipboardData failed (format {fmt})")


# ---- 逐字輸入：單批 SendInput（VK_PACKET unicode）----
# keyboard.write 逐字慢送（每字一次呼叫＋延遲）會與中文輸入法的非同步處理交錯：
# CJK 直接通過、全形標點被抓進組字緩衝，稍後整團吐出 → 標點錯位（實案「，，。」擠團）。
# 整句打包成一次 SendInput 原子性進輸入佇列即可避免，且長句即刻出字。
_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004
_VK_RETURN = 0x0D


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t))


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = (("ki", _KEYBDINPUT), ("_pad", ctypes.c_ubyte * 32))

    _anonymous_ = ("u",)
    _fields_ = (("type", wintypes.DWORD), ("u", _U))


_user32.SendInput.restype = wintypes.UINT
_user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]


def _utf16_units(text: str) -> list[int]:
    """展開為 UTF-16 編碼單元（BMP 一單元；增補平面代理對兩單元，Windows 會自行重組）。"""
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


# ---- 備份格式白名單（spec：圖片＋檔案＋富文字＋純文字）----
# 衍生格式（CF_TEXT/CF_OEMTEXT/CF_LOCALE←CF_UNICODETEXT、CF_BITMAP←CF_DIB）由
# Windows 自動合成，不備不還。具名格式編號動態配發，執行期解析。
_CF_DIBV5 = getattr(win32con, "CF_DIBV5", 17)
_FIXED_FORMATS = (win32con.CF_UNICODETEXT, win32con.CF_DIB, _CF_DIBV5,
                  win32con.CF_HDROP)
_NAMED_FORMATS = ("PNG", "Preferred DropEffect", "HTML Format",
                  "Rich Text Format")
_MAX_FMT_BYTES = 64 * 1024 * 1024     # 單格式上限（4K 截圖 DIB ≈ 33MB 安全通過）
_MAX_TOTAL_BYTES = 200 * 1024 * 1024  # 總量上限


def _whitelist() -> set[int]:
    ids = set(_FIXED_FORMATS)
    for name in _NAMED_FORMATS:
        ids.add(win32clipboard.RegisterClipboardFormat(name))
    return ids


def _snapshot_clipboard(max_fmt_bytes: int = _MAX_FMT_BYTES,
                        max_total_bytes: int = _MAX_TOTAL_BYTES,
                        ) -> list[tuple[int, bytes]] | None:
    """把剪貼簿上白名單格式的原始位元組全部拷出。回傳依原列舉順序的
    (format_id, bytes) 清單；重試後仍開不了剪貼簿回 None。"""
    wanted = _whitelist()
    err: Exception | None = None
    for _ in range(_CLIP_RETRIES):
        try:
            win32clipboard.OpenClipboard()
            try:
                items: list[tuple[int, bytes]] = []
                total = 0
                fmt = win32clipboard.EnumClipboardFormats(0)
                while fmt:
                    if fmt in wanted:
                        data = _read_format_bytes(fmt)
                        if data is None:
                            pass
                        elif len(data) > max_fmt_bytes:
                            log.warning("剪貼簿格式 %d 過大（%d bytes），略過",
                                        fmt, len(data))
                        elif total + len(data) > max_total_bytes:
                            log.warning("剪貼簿備份達總量上限，其餘格式略過")
                            break
                        else:
                            items.append((fmt, data))
                            total += len(data)
                    fmt = win32clipboard.EnumClipboardFormats(fmt)
                return items
            finally:
                win32clipboard.CloseClipboard()
        except Exception as e:  # noqa: BLE001 - 剪貼簿被鎖定等，重試
            err = e
            time.sleep(_CLIP_WAIT)
    log.warning("剪貼簿快照失敗（最後錯誤：%r），退回純文字備份", err)
    return None


def _restore_clipboard(items: list[tuple[int, bytes]]) -> None:
    """清空剪貼簿後把快照逐格式原樣放回（依快照順序＝原擁有者的優先順序）。"""
    err: Exception | None = None
    for _ in range(_CLIP_RETRIES):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                for fmt, data in items:
                    _write_format_bytes(fmt, data)
                return
            finally:
                win32clipboard.CloseClipboard()
        except Exception as e:  # noqa: BLE001 - 每輪從 Empty 重來，重試安全
            err = e
            time.sleep(_CLIP_WAIT)
    raise RuntimeError(f"無法還原剪貼簿（最後錯誤：{err!r}）")


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
    err: Exception | None = None
    for _ in range(_CLIP_RETRIES):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
                return
            finally:
                win32clipboard.CloseClipboard()
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(_CLIP_WAIT)
    raise RuntimeError(f"無法寫入剪貼簿（最後錯誤：{err!r}）")


def _multiformat_enabled() -> bool:
    """多格式還原總開關（config: clipboard_multiformat，預設關）。
    2026-07-12 兩份 crash dump 證實 0xc0000374 heap 損毀於 win32clipboard→user32
    呼叫中引爆，多格式快照/還原循環為觸發面（合成內容測不出、真實富內容＋
    並行讀者會中）。隔離待完整 dump 定位根因；設 True 可重新啟用參與獵殺。"""
    try:
        from app import config
        return bool(config.load().get("clipboard_multiformat", False))
    except Exception:  # noqa: BLE001 - 設定讀不到就走安全路徑
        return False


class ClipboardGuard:
    """進入時備份剪貼簿、離開時還原；還原重試撐過目標視窗的短暫鎖定。
    多格式模式（圖片/檔案/富文字位元組級快照）由 _multiformat_enabled 控制，
    預設關閉（穩定性隔離），關閉或快照失敗都退回純文字備份——備份問題絕不
    擋住貼上。原剪貼簿為空時不還原（辨識文字留在剪貼簿，保留手動 Ctrl+V 退路）。"""

    def __enter__(self):
        self._items: list[tuple[int, bytes]] | None = None
        self._text: str | None = None
        if _multiformat_enabled():
            try:
                self._items = _snapshot_clipboard()
            except Exception:  # noqa: BLE001
                log.warning("多格式快照失敗，退回純文字備份", exc_info=True)
        if self._items is None:
            self._text = _get_clipboard_text()
        return self

    def __exit__(self, *exc):
        try:
            if self._items:
                _restore_clipboard(self._items)
            elif self._items is None and self._text is not None:
                _set_clipboard_text(self._text)
        except RuntimeError:
            log.warning("還原剪貼簿失敗")
        return False


def inject_text(text: str, mode: str = "clipboard") -> bool:
    """回傳是否成功送出（僅代表動作完成，無法保證目標視窗接受）。"""
    if not text:
        return False
    try:
        if mode == "type":
            _type_text(text)
            return True
        from app.heapprobe import checkpoint  # 0xc0000374 排查探針，結案後移除
        try:
            with ClipboardGuard():
                checkpoint("剪貼簿寫入前")
                _set_clipboard_text(text)
                checkpoint("剪貼簿寫入後")
                time.sleep(0.05)       # 讓剪貼簿寫入落定
                keyboard.send("ctrl+v")
                time.sleep(0.2)        # 給目標視窗抓走內容的時間；離開時的還原會重試撐過鎖定
        except RuntimeError as e:
            # 剪貼簿被其他程式長時間鎖住（剪貼簿歷程/防毒都會在內容變動後搶開來讀）。
            # 寫不進就不硬撐：改逐字輸入，文字一樣送達，不再回報「處理失敗」。
            log.warning("剪貼簿寫入失敗（%s），改用逐字輸入送出", e)
            _type_text(text)
        return True
    except Exception:  # noqa: BLE001
        log.exception("inject failed")
        try:
            _set_clipboard_text(text)  # 失敗保底：至少把文字留在剪貼簿
        except RuntimeError:
            pass
        return False
