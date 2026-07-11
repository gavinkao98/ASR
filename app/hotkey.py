"""全域熱鍵 hook。攔截設定的鍵（suppress），長按=PTT、短按=補送原鍵。
提示音/浮窗只在「確認為長按」（過門檻仍按著）時才出現，避免一般短按也叫又閃。"""
import threading
import time

import keyboard

from app.logger import get_logger
from app.ptt_logic import PttStateMachine

log = get_logger("hotkey")


class HotkeyListener:
    def __init__(self, key: str, threshold_ms: int,
                 on_start, on_finish, on_hold=None):
        self._key = key
        self._threshold_ms = threshold_ms
        self._on_hold = on_hold          # 確認長按才觸發（提示音/浮窗）
        self._external_on_start = on_start
        self._external_on_finish = on_finish
        self._hold_timer = None
        self._sm = PttStateMachine(
            threshold_ms=threshold_ms,
            on_start=self._on_down,
            on_finish=self._on_up_hold,
            on_cancel_tap=self._on_up_tap,
        )
        self._hooks = []

    def _on_down(self) -> None:
        self._external_on_start()        # 立刻開始錄音（不漏字頭、且靜默）
        if self._on_hold is not None:    # 過門檻仍按著 → 才給提示音/浮窗
            self._cancel_hold_timer()
            self._hold_timer = threading.Timer(
                self._threshold_ms / 1000.0, self._fire_hold)
            self._hold_timer.daemon = True
            self._hold_timer.start()

    def _fire_hold(self) -> None:
        self._hold_timer = None
        if self._on_hold is not None:
            self._on_hold()

    def _cancel_hold_timer(self) -> None:
        if self._hold_timer is not None:
            self._hold_timer.cancel()
            self._hold_timer = None

    def _on_up_hold(self) -> None:
        self._cancel_hold_timer()        # 通常已觸發，保險起見
        self._external_on_finish()

    def _on_up_tap(self) -> None:
        # 短按：取消尚未觸發的提示音/浮窗（沒過門檻不打擾），並補送原按鍵行為
        self._cancel_hold_timer()
        keyboard.send(self._key)

    def _on_key_event(self, e) -> None:
        t = time.monotonic() * 1000
        if e.event_type == keyboard.KEY_DOWN:
            self._sm.key_down(t)
        elif e.event_type == keyboard.KEY_UP:
            self._sm.key_up(t)

    def start(self) -> None:
        # 用單一 hook_key（同時收 down/up）而非 on_press_key + on_release_key 兩個 hook：
        # 後者對同一個鍵在 keyboard 套件內部共用同一個 key 條目，解除第二個時會丟
        # KeyError，害「結束/暫停」在真正退出前中斷、hook 殘留、CapsLock 被卡住。
        self._hooks.append(
            keyboard.hook_key(self._key, self._on_key_event, suppress=True))
        log.info("hotkey armed: %s", self._key)

    def stop(self) -> None:
        self._cancel_hold_timer()
        for h in self._hooks:
            try:
                keyboard.unhook(h)
            except (KeyError, ValueError):  # 保險：keyboard 解除偶發重複刪同一 key
                pass
        self._hooks = []
