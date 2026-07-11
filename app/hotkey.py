"""全域熱鍵 hook。攔截設定的鍵（suppress），長按=PTT、短按=補送原鍵。
提示音/浮窗只在「確認為長按」（過門檻仍按著）時才出現，避免一般短按也叫又閃。

重要：低階鍵盤 hook 的回呼必須「立刻返回」。若在 hook 執行緒裡做開/關麥克風這類可能耗時的
動作，會超過 Windows 的 LowLevelHooksTimeout、被系統整個移除 hook，導致「放開鍵」的事件收不
到、錄音停不下來。因此 hook 只負責「記下時間、丟進工作佇列」就返回；狀態機與所有外部回呼
（開始/結束/取消錄音、補送原鍵）一律在背景工作執行緒執行。
"""
import queue
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
        # 背景工作佇列：hook 執行緒只丟工作、瞬間返回；實際（可能耗時的）動作在這條執行緒跑，
        # 確保 hook 回呼永不阻塞、不被 Windows 逾時移除。
        self._cmd_q: queue.Queue = queue.Queue()
        threading.Thread(target=self._cmd_loop, daemon=True).start()

    def _cmd_loop(self) -> None:
        while True:
            fn = self._cmd_q.get()
            try:
                fn()
            except Exception:  # noqa: BLE001 - 單一動作出錯不可拖垮整條工作執行緒
                log.exception("hotkey worker error")

    def _on_down(self) -> None:
        # 先排長按計時器（門檻要從「按下」起算才準），再開始錄音（可能耗時，已在工作執行緒）。
        if self._on_hold is not None:    # 過門檻仍按著 → 才給提示音/浮窗
            self._cancel_hold_timer()
            self._hold_timer = threading.Timer(
                self._threshold_ms / 1000.0, self._fire_hold)
            self._hold_timer.daemon = True
            self._hold_timer.start()
        self._external_on_start()        # 立刻開始錄音（不漏字頭、且靜默）

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
        # 只做「記時間 + 丟佇列」就返回（回傳 None → 事件被 suppress）；狀態機與外部回呼都在
        # 工作執行緒跑，不阻塞 hook，放開鍵的事件才不會因逾時被系統丟掉。
        t = time.monotonic() * 1000
        if e.event_type == keyboard.KEY_DOWN:
            self._cmd_q.put(lambda: self._sm.key_down(t))
        elif e.event_type == keyboard.KEY_UP:
            self._cmd_q.put(lambda: self._sm.key_up(t))

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
