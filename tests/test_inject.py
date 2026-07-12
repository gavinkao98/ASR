"""inject 編排層：逐字單批輸出＋剪貼簿替身流程（真替身端到端，Ctrl+V 以假鍵代替）。"""
import pytest

from app import clipwin, inject


# ---- 逐字輸入：單批 SendInput ----
def test_utf16_units_bmp_and_surrogate():
    assert inject._utf16_units("你a") == [0x4F60, 0x61]
    assert inject._utf16_units("\U0001D11E") == [0xD834, 0xDD1E]  # 代理對


def test_type_text_sends_single_batch(monkeypatch):
    """整句必須打包成單一批次：逐字慢送會被輸入法插隊、標點錯位（「，，。」擠團）。"""
    batches = []
    monkeypatch.setattr(inject, "_send_unicode_batch", batches.append)
    inject._type_text("直接輸出，保留。")
    assert batches == [inject._utf16_units("直接輸出，保留。")]


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


# ---- 剪貼簿模式：替身編排 ----
def test_clipboard_mode_via_real_helper_restores(monkeypatch):
    """端到端（假 Ctrl+V）：替身備妥→貼上→還原，原剪貼簿多格式內容原樣回歸。"""
    fmt_png = clipwin.register_format("PNG")
    with clipwin.open_clipboard():
        clipwin.empty_clipboard()
        clipwin.write_format_bytes(clipwin.CF_UNICODETEXT, "原有\0".encode("utf-16-le"))
        clipwin.write_format_bytes(fmt_png, b"marker-png")

    pasted = []
    monkeypatch.setattr(inject, "_multiformat_enabled", lambda: True)  # 不依賴使用者 config
    monkeypatch.setattr(inject.keyboard, "send", lambda *a: pasted.append(a))
    seen_at_paste = []
    monkeypatch.setattr(inject.time, "sleep",
                        lambda s: seen_at_paste.append(clipwin.get_text()))

    assert inject.inject_text("辨識結果", "clipboard") is True
    assert pasted == [("ctrl+v",)]
    assert "辨識結果" in seen_at_paste          # 按下 Ctrl+V 當下剪貼簿是新文字
    assert clipwin.get_text() == "原有"          # 事後原內容還原
    with clipwin.open_clipboard():
        assert clipwin.read_format_bytes(fmt_png) == b"marker-png"
    inject._helper.kill()                        # 測試收尾，不留常駐行程


def test_clipboard_mode_falls_back_to_typing_when_helper_dead(monkeypatch):
    typed, pasted = [], []
    monkeypatch.setattr(inject._helper, "begin", lambda *a, **k: False)
    monkeypatch.setattr(inject, "_type_text", typed.append)
    monkeypatch.setattr(inject.keyboard, "send", lambda *a: pasted.append(a))
    assert inject.inject_text("四零九六", "clipboard") is True
    assert typed == ["四零九六"]   # 文字仍送達
    assert pasted == []            # 沒有替身就不按 Ctrl+V


def test_empty_text_rejected():
    assert inject.inject_text("", "clipboard") is False


def test_begin_timeout_kills_and_reports_false(monkeypatch):
    """替身裝死（不回 READY）→ begin False 並收屍，下次自動重生。"""
    class FakeProc:
        def __init__(self):
            self.killed = False
            self.stdin = self
            self.stdout = self
        def poll(self): return None
        def write(self, *_): return None
        def flush(self): return None
        def readline(self): import time; time.sleep(10); return b""
        def kill(self): self.killed = True

    fake = FakeProc()
    client = inject._HelperClient()
    client._proc = fake
    monkeypatch.setattr(client, "_read_line", lambda t: None)  # 模擬逾時
    assert client.begin("x", True) is False
    assert fake.killed is True
