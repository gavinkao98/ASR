from typing import Callable


class PttStateMachine:
    """push-to-talk 判定。時間由外部注入（毫秒），純邏輯零 OS 依賴。"""

    def __init__(self, threshold_ms: int,
                 on_start: Callable, on_finish: Callable, on_cancel_tap: Callable):
        self._threshold = threshold_ms
        self._on_start = on_start
        self._on_finish = on_finish
        self._on_cancel_tap = on_cancel_tap
        self._down_at: float | None = None

    def key_down(self, t_ms: float) -> None:
        if self._down_at is not None:
            return  # auto-repeat
        self._down_at = t_ms
        self._on_start()

    def key_up(self, t_ms: float) -> None:
        if self._down_at is None:
            return
        held = t_ms - self._down_at
        self._down_at = None
        if held < self._threshold:
            self._on_cancel_tap()
        else:
            self._on_finish()
