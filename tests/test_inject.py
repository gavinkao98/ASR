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


def test_snapshot_then_restore_roundtrip():
    fmt_html = win32clipboard.RegisterClipboardFormat("HTML Format")
    html = b"<html><body>hi</body></html>"
    _put_formats([(win32con.CF_UNICODETEXT, "原文\0".encode("utf-16-le")),
                  (fmt_html, html)])
    saved = inject._snapshot_clipboard()
    _set_clipboard_text("蓋掉")             # 模擬貼上流程覆寫
    inject._restore_clipboard(saved)
    assert _peek_format(fmt_html) == html   # 位元組級還原
    assert _get_clipboard_text() == "原文"


def test_guard_multiformat_off_by_default_restores_text_only(monkeypatch):
    """隔離措施：多格式還原預設關閉（0xc0000374 排查中），退回純文字備份。"""
    monkeypatch.setattr(inject, "_multiformat_enabled", lambda: False, raising=False)
    fmt_png = win32clipboard.RegisterClipboardFormat("PNG")
    _put_formats([(win32con.CF_UNICODETEXT, "原字\0".encode("utf-16-le")),
                  (fmt_png, b"img")])
    with ClipboardGuard():
        _set_clipboard_text("辨識結果")
    assert _get_clipboard_text() == "原字"   # 文字照樣還原（舊行為）
    assert _peek_format(fmt_png) is None     # 圖片不還原＝多格式路徑確實沒跑


def _minimal_dib() -> bytes:
    """2x2、24bpp、BI_RGB 的最小合法 DIB（BITMAPINFOHEADER＋補齊到 4 bytes 的像素列）。"""
    header = struct.pack("<IiiHHIIiiII", 40, 2, 2, 1, 24, 0, 16, 0, 0, 0, 0)
    return header + bytes(16)


def test_guard_restores_image_and_text_together(monkeypatch):
    monkeypatch.setattr(inject, "_multiformat_enabled", lambda: True, raising=False)
    dib = _minimal_dib()
    _put_formats([(win32con.CF_UNICODETEXT, "原本\0".encode("utf-16-le")),
                  (win32con.CF_DIB, dib)])
    with ClipboardGuard():
        _set_clipboard_text("辨識結果")
    assert _peek_format(win32con.CF_DIB) == dib      # 圖片位元組級還原
    assert _get_clipboard_text() == "原本"
    win32clipboard.OpenClipboard()                    # Windows 由 DIB 自動合成 CF_BITMAP
    try:
        assert win32clipboard.IsClipboardFormatAvailable(win32con.CF_BITMAP)
    finally:
        win32clipboard.CloseClipboard()


def test_guard_restores_file_list(monkeypatch):
    monkeypatch.setattr(inject, "_multiformat_enabled", lambda: True, raising=False)
    # DROPFILES 結構：pFiles=20、pt=(0,0)、fNC=0、fWide=1，接 UTF-16LE 路徑清單（雙 \0 結尾）
    path = "C:\\Windows\\notepad.exe"
    dropfiles = struct.pack("<IiiII", 20, 0, 0, 0, 1)
    hdrop = dropfiles + (path + "\0\0").encode("utf-16-le")
    fmt_effect = win32clipboard.RegisterClipboardFormat("Preferred DropEffect")
    _put_formats([(win32con.CF_HDROP, hdrop),
                  (fmt_effect, struct.pack("<I", 5))])  # DROPEFFECT_COPY|LINK＝檔案總管「複製」
    with ClipboardGuard():
        _set_clipboard_text("辨識結果")
    win32clipboard.OpenClipboard()
    try:  # 用 pywin32 原生解析驗證（證明 Windows 認得我們還原的結構，非自說自話）
        assert win32clipboard.GetClipboardData(win32con.CF_HDROP) == (path,)
    finally:
        win32clipboard.CloseClipboard()
    assert _peek_format(fmt_effect) == struct.pack("<I", 5)


def test_guard_falls_back_to_text_when_snapshot_raises(monkeypatch):
    monkeypatch.setattr(inject, "_multiformat_enabled", lambda: True, raising=False)
    _set_clipboard_text("退路文字")
    monkeypatch.setattr(inject, "_snapshot_clipboard",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with ClipboardGuard():
        _set_clipboard_text("辨識結果")
    assert _get_clipboard_text() == "退路文字"  # 快照炸掉仍以舊路徑還原文字


def test_guard_empty_clipboard_keeps_pasted_text(monkeypatch):
    monkeypatch.setattr(inject, "_multiformat_enabled", lambda: True, raising=False)
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()  # 原本就空
    finally:
        win32clipboard.CloseClipboard()
    with ClipboardGuard():
        _set_clipboard_text("辨識結果")
    assert _get_clipboard_text() == "辨識結果"  # 維持現行為：辨識文字留著（手動 Ctrl+V 退路）


def test_utf16_units_bmp_and_surrogate():
    """逐字輸出的 UTF-16 編碼單元展開：BMP 單元、增補平面成對（emoji 等）。"""
    assert inject._utf16_units("你a") == [0x4F60, 0x61]
    assert inject._utf16_units("\U0001D11E") == [0xD834, 0xDD1E]  # 代理對


def test_type_text_sends_single_batch(monkeypatch):
    """整句必須打包成單一批次送出：逐字慢送會被輸入法插隊、標點錯位
    （實案：「，，。」全擠在句首後方）。"""
    batches = []
    monkeypatch.setattr(inject, "_send_unicode_batch", batches.append)
    inject._type_text("直接輸出，保留。")
    assert len(batches) == 1                      # 一句一批，不逐字
    assert batches[0] == inject._utf16_units("直接輸出，保留。")


def test_type_text_newline_becomes_enter(monkeypatch):
    calls = []
    monkeypatch.setattr(inject, "_send_unicode_batch", lambda u: calls.append(("uni", u)))
    monkeypatch.setattr(inject, "_send_enter", lambda: calls.append(("enter",)))
    inject._type_text("上\n下")
    assert calls == [("uni", inject._utf16_units("上")), ("enter",),
                     ("uni", inject._utf16_units("下"))]


def test_inject_type_mode_uses_batch_typing(monkeypatch):
    typed = []
    monkeypatch.setattr(inject, "_type_text", typed.append)
    assert inject.inject_text("測試句", "type") is True
    assert typed == ["測試句"]


def test_inject_falls_back_to_typing_when_clipboard_locked(monkeypatch):
    """剪貼簿被鎖（剪貼簿歷程/防毒長時間占用）時不整次失敗：改逐字輸入送出。
    實案：asr.log 10:04 三次「無法寫入剪貼簿」，辨識全對卻顯示處理失敗。"""
    typed, pasted = [], []
    monkeypatch.setattr(inject, "_set_clipboard_text",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("locked")))
    monkeypatch.setattr(inject, "_type_text", typed.append)
    monkeypatch.setattr(inject.keyboard, "send", lambda *a: pasted.append(a))
    assert inject.inject_text("四零九六", "clipboard") is True
    assert typed == ["四零九六"]   # 文字仍送達
    assert pasted == []            # Ctrl+V 沒有發（剪貼簿路線放棄）


def test_set_clipboard_error_reports_cause(monkeypatch):
    """重試耗盡時要帶出最後一次的底層錯誤，不能只說「無法寫入」。"""
    monkeypatch.setattr(inject, "_CLIP_RETRIES", 2)
    monkeypatch.setattr(inject, "_CLIP_WAIT", 0)
    monkeypatch.setattr(inject.win32clipboard, "OpenClipboard",
                        lambda *a: (_ for _ in ()).throw(ValueError("boom-cause")))
    with pytest.raises(RuntimeError, match="boom-cause"):
        _set_clipboard_text("x")


def test_clipboard_roundtrip():
    _set_clipboard_text("測試123 English")
    assert _get_clipboard_text() == "測試123 English"


def test_guard_restores_text():
    _set_clipboard_text("原本的內容")
    with ClipboardGuard() as g:
        _set_clipboard_text("暫時的內容")
    assert _get_clipboard_text() == "原本的內容"
