"""熱鍵 hook 回呼不可阻塞：即使外部 on_start（開麥克風）很慢，_on_key_event 也要瞬間返回、
動作在工作執行緒跑。否則會超過 Windows LowLevelHooksTimeout、整個 hook 被系統移除，導致
「放開鍵」的事件收不到、錄音停不下來（實際回報過的 bug）。這些測試只直接呼叫 _on_key_event，
不掛全域 hook、也不走短按補送鍵路徑，故不會干擾測試機的鍵盤。"""
import threading
import time

import keyboard

from app.hotkey import HotkeyListener


class _FakeEvent:
    def __init__(self, event_type):
        self.event_type = event_type
        self.scan_code = 58  # caps lock


def test_on_key_event_returns_immediately_despite_slow_callback():
    started = threading.Event()
    finished = threading.Event()

    def slow_on_start():
        started.set()
        time.sleep(0.5)      # 模擬開麥克風耗時（> 300ms hook 逾時門檻）
        finished.set()

    hl = HotkeyListener("caps lock", 300, on_start=slow_on_start,
                        on_finish=lambda: None, on_hold=None)

    t0 = time.monotonic()
    hl._on_key_event(_FakeEvent(keyboard.KEY_DOWN))
    elapsed = time.monotonic() - t0

    assert elapsed < 0.1, f"_on_key_event 阻塞了 {elapsed:.2f}s，應瞬間返回（動作要丟到工作執行緒）"
    assert started.wait(1.0), "on_start 應在背景工作執行緒被呼叫"
    assert finished.wait(1.0)


def test_hold_then_release_fires_finish_via_worker():
    calls = []
    hl = HotkeyListener("caps lock", 300,
                        on_start=lambda: calls.append("start"),
                        on_finish=lambda: calls.append("finish"), on_hold=None)
    hl._on_key_event(_FakeEvent(keyboard.KEY_DOWN))
    time.sleep(0.35)         # 撐過 300ms 門檻 → 放開走 finish（非短按 cancel）
    hl._on_key_event(_FakeEvent(keyboard.KEY_UP))
    time.sleep(0.1)          # 等工作執行緒跑完
    assert calls == ["start", "finish"]
