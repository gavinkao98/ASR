import struct

import pytest
import win32clipboard
import win32con

from app import inject
from app.inject import ClipboardGuard, _get_clipboard_text, _set_clipboard_text


def _put_formats(items):
    """直接把 (format_id, bytes) 塞進真剪貼簿（測試備妥狀態用）。"""
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        for fmt, data in items:
            inject._write_format_bytes(fmt, data)
    finally:
        win32clipboard.CloseClipboard()


def _peek_format(fmt):
    """讀出真剪貼簿上某格式的原始位元組（無此格式回 None）。"""
    win32clipboard.OpenClipboard()
    try:
        return inject._read_format_bytes(fmt)
    finally:
        win32clipboard.CloseClipboard()


def test_raw_bytes_roundtrip_registered_format():
    fmt = win32clipboard.RegisterClipboardFormat("PNG")
    payload = b"\x89PNG-fake-payload-123"
    _put_formats([(fmt, payload)])
    assert _peek_format(fmt) == payload


def test_snapshot_collects_whitelisted_formats():
    fmt_png = win32clipboard.RegisterClipboardFormat("PNG")
    _put_formats([(win32con.CF_UNICODETEXT, "哈囉\0".encode("utf-16-le")),
                  (fmt_png, b"png-bytes")])
    items = dict(inject._snapshot_clipboard())
    assert items[fmt_png] == b"png-bytes"
    assert win32con.CF_UNICODETEXT in items


def test_snapshot_skips_oversized_format_keeps_rest():
    fmt_png = win32clipboard.RegisterClipboardFormat("PNG")
    _put_formats([(win32con.CF_UNICODETEXT, "小\0".encode("utf-16-le")),
                  (fmt_png, b"x" * 200)])
    items = dict(inject._snapshot_clipboard(max_fmt_bytes=100))
    assert fmt_png not in items          # 超過單格式上限 → 跳過
    assert win32con.CF_UNICODETEXT in items  # 其他格式照常


def test_snapshot_total_cap_stops_collecting():
    fmt_png = win32clipboard.RegisterClipboardFormat("PNG")
    fmt_html = win32clipboard.RegisterClipboardFormat("HTML Format")
    _put_formats([(fmt_png, b"a" * 80), (fmt_html, b"b" * 80)])
    items = inject._snapshot_clipboard(max_total_bytes=100)
    assert len(items) == 1               # 收了第一個之後達總量上限即停


def test_clipboard_roundtrip():
    _set_clipboard_text("測試123 English")
    assert _get_clipboard_text() == "測試123 English"


def test_guard_restores_text():
    _set_clipboard_text("原本的內容")
    with ClipboardGuard() as g:
        _set_clipboard_text("暫時的內容")
    assert _get_clipboard_text() == "原本的內容"
