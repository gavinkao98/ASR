"""全域熱鍵 hook。攔截設定的鍵（suppress），長按=PTT、短按=補送原鍵。"""
import time

import keyboard

from app.logger import get_logger
from app.ptt_logic import PttStateMachine

log = get_logger("hotkey")


class HotkeyListener:
    def __init__(self, key: str, threshold_ms: int,
                 on_start, on_finish):
        self._key = key
        self._sm = PttStateMachine(
            threshold_ms=threshold_ms,
            on_start=on_start, on_finish=on_finish,
            on_cancel_tap=self._replay_tap,
        )
        self._hooks = []

    def _replay_tap(self) -> None:
        # 短按：把被 suppress 的原按鍵行為補回去（CapsLock 開關等）
        keyboard.send(self._key)

    def start(self) -> None:
        self._hooks.append(keyboard.on_press_key(
            self._key, lambda e: self._sm.key_down(time.monotonic() * 1000),
            suppress=True))
        self._hooks.append(keyboard.on_release_key(
            self._key, lambda e: self._sm.key_up(time.monotonic() * 1000),
            suppress=True))
        log.info("hotkey armed: %s", self._key)

    def stop(self) -> None:
        for h in self._hooks:
            keyboard.unhook(h)
        self._hooks = []
