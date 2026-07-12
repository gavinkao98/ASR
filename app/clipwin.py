"""純 ctypes 剪貼簿原語——零第三方依賴（pywin32-free）、不 import app.*。

供兩邊共用：主行程 `from app import clipwin`；替身子行程（clipboard_helper.py）
在同目錄以 `import clipwin` 載入，讓 `pythonw -S -E` 極速啟動。
所有「多格式白名單快照/還原」邏輯集中於此（原 app/inject.py 遷入）。
"""
import ctypes
import time
from ctypes import wintypes

_u32 = ctypes.windll.user32
_k32 = ctypes.windll.kernel32

_u32.OpenClipboard.restype = wintypes.BOOL
_u32.OpenClipboard.argtypes = [wintypes.HWND]
_u32.CloseClipboard.restype = wintypes.BOOL
_u32.EmptyClipboard.restype = wintypes.BOOL
_u32.EnumClipboardFormats.restype = wintypes.UINT
_u32.EnumClipboardFormats.argtypes = [wintypes.UINT]
_u32.RegisterClipboardFormatW.restype = wintypes.UINT
_u32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
_u32.IsClipboardFormatAvailable.restype = wintypes.BOOL
_u32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
_u32.GetClipboardData.restype = wintypes.HANDLE
_u32.GetClipboardData.argtypes = [wintypes.UINT]
_u32.SetClipboardData.restype = wintypes.HANDLE
_u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_k32.GlobalSize.restype = ctypes.c_size_t
_k32.GlobalSize.argtypes = [wintypes.HGLOBAL]
_k32.GlobalLock.restype = wintypes.LPVOID
_k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_k32.GlobalUnlock.restype = wintypes.BOOL
_k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_k32.GlobalAlloc.restype = wintypes.HGLOBAL
_k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_k32.GlobalFree.restype = wintypes.HGLOBAL
_k32.GlobalFree.argtypes = [wintypes.HGLOBAL]

_GMEM_MOVEABLE = 0x0002
CF_UNICODETEXT = 13
CF_DIB = 8
CF_DIBV5 = 17
CF_HDROP = 15

RETRIES = 20      # 剪貼簿被短暫鎖定時的重試次數
WAIT = 0.05       # 每次重試間隔（秒）

# 備份白名單：衍生格式（CF_TEXT/CF_OEMTEXT/CF_LOCALE←CF_UNICODETEXT、CF_BITMAP←CF_DIB）
# 由 Windows 自動合成，不備不還；具名格式編號動態配發，執行期解析。
_FIXED_FORMATS = (CF_UNICODETEXT, CF_DIB, CF_DIBV5, CF_HDROP)
_NAMED_FORMATS = ("PNG", "Preferred DropEffect", "HTML Format", "Rich Text Format")
MAX_FMT_BYTES = 64 * 1024 * 1024      # 單格式上限（4K 截圖 DIB ≈ 33MB 安全通過）
MAX_TOTAL_BYTES = 200 * 1024 * 1024   # 總量上限


class open_clipboard:
    """開啟剪貼簿的 context manager；重試撐過其他行程的短暫鎖定。"""

    def __enter__(self):
        for _ in range(RETRIES):
            if _u32.OpenClipboard(None):
                return self
            time.sleep(WAIT)
        raise RuntimeError("無法開啟剪貼簿（持續被占用）")

    def __exit__(self, *exc):
        _u32.CloseClipboard()
        return False


def empty_clipboard() -> None:
    _u32.EmptyClipboard()


def register_format(name: str) -> int:
    return _u32.RegisterClipboardFormatW(name)


def read_format_bytes(fmt: int) -> bytes | None:
    """讀某格式整塊原始位元組（呼叫前剪貼簿必須已開）。非 HGLOBAL／空資料回 None。"""
    h = _u32.GetClipboardData(fmt)
    if not h:
        return None
    size = _k32.GlobalSize(h)
    if not size:
        return None
    ptr = _k32.GlobalLock(h)
    if not ptr:
        return None
    try:
        return ctypes.string_at(ptr, size)
    finally:
        _k32.GlobalUnlock(h)


def write_format_bytes(fmt: int, data: bytes) -> None:
    """原樣寫回某格式（呼叫前剪貼簿必須已開）。SetClipboardData 成功後記憶體歸系統，
    失敗才由我們 GlobalFree。"""
    h = _k32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
    if not h:
        raise MemoryError("GlobalAlloc failed")
    ptr = _k32.GlobalLock(h)
    if not ptr:
        _k32.GlobalFree(h)
        raise MemoryError("GlobalLock failed")
    ctypes.memmove(ptr, data, len(data))
    _k32.GlobalUnlock(h)
    if not _u32.SetClipboardData(fmt, h):
        _k32.GlobalFree(h)
        raise RuntimeError(f"SetClipboardData failed (format {fmt})")


def get_text() -> str | None:
    """讀 CF_UNICODETEXT；剪貼簿開不了或無文字回 None。"""
    try:
        with open_clipboard():
            if not _u32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                return None
            raw = read_format_bytes(CF_UNICODETEXT)
    except RuntimeError:
        return None
    if raw is None:
        return None
    return raw.decode("utf-16-le", errors="ignore").split("\x00", 1)[0]


def set_text(text: str) -> None:
    """清空後寫入 CF_UNICODETEXT；重試耗盡帶出最後錯誤。"""
    payload = (text + "\x00").encode("utf-16-le")
    err: Exception | None = None
    for _ in range(RETRIES):
        try:
            with open_clipboard():
                empty_clipboard()
                write_format_bytes(CF_UNICODETEXT, payload)
                return
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(WAIT)
    raise RuntimeError(f"無法寫入剪貼簿（最後錯誤：{err!r}）")


def _whitelist() -> set[int]:
    ids = set(_FIXED_FORMATS)
    for name in _NAMED_FORMATS:
        ids.add(register_format(name))
    return ids


def snapshot(max_fmt_bytes: int = MAX_FMT_BYTES,
             max_total_bytes: int = MAX_TOTAL_BYTES) -> list[tuple[int, bytes]] | None:
    """拷出白名單格式的原始位元組，依原列舉順序；開不了剪貼簿回 None。
    超過單格式上限跳過該格式；達總量上限停止收集（其餘照常）。"""
    wanted = _whitelist()
    err: Exception | None = None
    for _ in range(RETRIES):
        try:
            with open_clipboard():
                items: list[tuple[int, bytes]] = []
                total = 0
                fmt = _u32.EnumClipboardFormats(0)
                while fmt:
                    if fmt in wanted:
                        data = read_format_bytes(fmt)
                        if data is None:
                            pass
                        elif len(data) > max_fmt_bytes:
                            pass                     # 過大：跳過該格式
                        elif total + len(data) > max_total_bytes:
                            break                    # 總量到頂：停止收集
                        else:
                            items.append((fmt, data))
                            total += len(data)
                    fmt = _u32.EnumClipboardFormats(fmt)
                return items
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(WAIT)
    del err
    return None


def restore(items: list[tuple[int, bytes]]) -> None:
    """清空後把快照逐格式原樣放回（依快照順序＝原擁有者優先序）。"""
    err: Exception | None = None
    for _ in range(RETRIES):
        try:
            with open_clipboard():
                empty_clipboard()
                for fmt, data in items:
                    write_format_bytes(fmt, data)
                return
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(WAIT)
    raise RuntimeError(f"無法還原剪貼簿（最後錯誤：{err!r}）")
