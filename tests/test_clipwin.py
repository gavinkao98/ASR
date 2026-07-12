"""clipwin：純 ctypes 剪貼簿原語（真剪貼簿 roundtrip；案例自 test_inject 遷移）。"""
import struct

from app import clipwin


def _put(items):
    with clipwin.open_clipboard():
        clipwin.empty_clipboard()
        for fmt, data in items:
            clipwin.write_format_bytes(fmt, data)


def _peek(fmt):
    with clipwin.open_clipboard():
        return clipwin.read_format_bytes(fmt)


def test_text_roundtrip():
    clipwin.set_text("測試123 English")
    assert clipwin.get_text() == "測試123 English"


def test_raw_bytes_roundtrip_registered_format():
    fmt = clipwin.register_format("PNG")
    payload = b"\x89PNG-fake-payload-123"
    _put([(fmt, payload)])
    assert _peek(fmt) == payload


def test_snapshot_collects_whitelisted_formats():
    fmt_png = clipwin.register_format("PNG")
    _put([(clipwin.CF_UNICODETEXT, "哈囉\0".encode("utf-16-le")),
          (fmt_png, b"png-bytes")])
    items = dict(clipwin.snapshot())
    assert items[fmt_png] == b"png-bytes"
    assert clipwin.CF_UNICODETEXT in items


def test_snapshot_skips_oversized_format_keeps_rest():
    fmt_png = clipwin.register_format("PNG")
    _put([(clipwin.CF_UNICODETEXT, "小\0".encode("utf-16-le")),
          (fmt_png, b"x" * 200)])
    items = dict(clipwin.snapshot(max_fmt_bytes=100))
    assert fmt_png not in items
    assert clipwin.CF_UNICODETEXT in items


def test_snapshot_total_cap_stops_collecting():
    fmt_png = clipwin.register_format("PNG")
    fmt_html = clipwin.register_format("HTML Format")
    _put([(fmt_png, b"a" * 80), (fmt_html, b"b" * 80)])
    assert len(clipwin.snapshot(max_total_bytes=100)) == 1


def test_snapshot_then_restore_roundtrip():
    fmt_html = clipwin.register_format("HTML Format")
    html = b"<html><body>hi</body></html>"
    _put([(clipwin.CF_UNICODETEXT, "原文\0".encode("utf-16-le")), (fmt_html, html)])
    saved = clipwin.snapshot()
    clipwin.set_text("蓋掉")
    clipwin.restore(saved)
    assert _peek(fmt_html) == html
    assert clipwin.get_text() == "原文"


def test_restore_hdrop_windows_parseable():
    """還原的 DROPFILES 要能被 Windows 原生解析（用 pywin32 驗證，非自說自話）。"""
    import win32clipboard
    import win32con
    path = "C:\\Windows\\notepad.exe"
    hdrop = struct.pack("<IiiII", 20, 0, 0, 0, 1) + (path + "\0\0").encode("utf-16-le")
    _put([(clipwin.CF_HDROP, hdrop)])
    saved = clipwin.snapshot()
    clipwin.set_text("蓋掉")
    clipwin.restore(saved)
    win32clipboard.OpenClipboard()
    try:
        assert win32clipboard.GetClipboardData(win32con.CF_HDROP) == (path,)
    finally:
        win32clipboard.CloseClipboard()
