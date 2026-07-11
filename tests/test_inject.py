import pytest

from app.inject import ClipboardGuard, _get_clipboard_text, _set_clipboard_text


def test_clipboard_roundtrip():
    _set_clipboard_text("測試123 English")
    assert _get_clipboard_text() == "測試123 English"


def test_guard_restores_text():
    _set_clipboard_text("原本的內容")
    with ClipboardGuard() as g:
        _set_clipboard_text("暫時的內容")
    assert _get_clipboard_text() == "原本的內容"
