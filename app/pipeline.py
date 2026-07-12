"""主協調器：熱鍵事件進、貼字出。辨識在單一 worker 執行緒跑，避免卡 hook 執行緒。"""
import queue
import threading

from app.logger import get_logger

log = get_logger("pipeline")


class Pipeline:
    def __init__(self, *, recorder, engines, vad_fn, chain_factory,
                 inject_fn, history_add, notify, paste_mode: str):
        self._recorder = recorder
        self._engines = engines
        self._vad_fn = vad_fn
        self._chain_factory = chain_factory
        self._inject_fn = inject_fn
        self._history_add = history_add
        self._notify = notify  # notify(kind): "start"|"empty"|"done"|"error"|"busy"
        self.paste_mode = paste_mode
        self._q: queue.Queue = queue.Queue()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()
        self.recording = False

    # ---- 由熱鍵執行緒呼叫（必須輕、快）----
    def on_record_start(self) -> None:
        if self._engines.state != "ready":
            self._notify("busy")
            return
        try:
            self._recorder.start()
        except Exception:  # noqa: BLE001 - 連預設麥克風都開不起來
            log.exception("recorder start failed")
            self._notify("error")
            return
        self.recording = True
        # 提示音/浮窗改由熱鍵層在「確認長按（過門檻）」時才觸發（見 hotkey on_hold），
        # 這樣一般短按 CapsLock 不會叫也不會閃。

    def on_record_finish(self) -> None:
        if not self.recording:
            return
        self.recording = False
        audio = self._recorder.stop()
        self._q.put(audio)

    def on_record_cancel(self) -> None:  # 短按（tap）時呼叫
        if self.recording:
            self.recording = False
            self._recorder.stop()

    # ---- worker ----
    def _run(self) -> None:
        while True:
            audio = self._q.get()
            try:
                self._process(audio)
            except Exception:  # noqa: BLE001
                log.exception("pipeline error")
                self._notify("error")
            finally:
                self._q.task_done()

    def _process(self, audio) -> None:
        from app.heapprobe import checkpoint  # 0xc0000374 排查探針，結案後移除
        checkpoint("進入處理")
        speech = self._vad_fn(audio)
        checkpoint("vad後")
        if speech is None or len(speech) == 0:
            self._notify("empty")
            return
        engine, raw = self._engines.transcribe(speech)   # 鎖內辨識，切換引擎時不會被卸載
        checkpoint("asr後")
        text = self._chain_factory(engine)(raw)
        checkpoint("chain後")
        if not text:
            self._notify("empty")
            return
        ok = self._inject_fn(text, self.paste_mode)
        checkpoint("inject後")
        self._history_add(text, engine.name)
        self._notify("done" if ok else "error")

    def join(self) -> None:  # 測試用
        self._q.join()
