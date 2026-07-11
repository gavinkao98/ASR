"""pywebview js_api。方法名/回傳格式=前端契約（Task 22 表），不可改簽名。"""
import threading

from app import config, downloads
from app.paths import HOTWORDS_FILE
from app.logger import get_logger

log = get_logger("bridge")
VERSION = "1.0.0"


class Bridge:
    def __init__(self, app):
        self._app = app  # 提供 switch_engine_async / apply_config_side_effects /
        #                  set_autostart / engines / pipeline / recorder（見 Task 24）
        self._dl = {"active": False, "progress": 0.0, "label": ""}

    # ---- 狀態 ----
    def get_state(self):
        engines = getattr(self._app, "engines", None)
        pipeline = getattr(self._app, "pipeline", None)
        cfg = config.load()
        return {"engine": cfg["engine"],
                "engine_state": engines.state if engines else "idle",
                "recording": bool(pipeline and pipeline.recording),
                "first_run_done": cfg["first_run_done"],
                "version": VERSION}

    def get_config(self):
        return config.load()

    def set_config(self, patch: dict):
        cfg = config.update(patch)
        self._app.apply_config_side_effects(patch)
        return cfg

    # ---- 裝置 ----
    def list_mics(self):
        from app.audio.recorder import Recorder
        return Recorder.list_devices()

    # ---- 引擎 ----
    def get_engines(self):
        cfg = config.load()
        return {"breeze": {"ready": downloads.breeze_ready(),
                           "active": cfg["engine"] == "breeze"},
                "qwen3": {"ready": downloads.qwen3_ready(),
                          "active": cfg["engine"] == "qwen3"}}

    def switch_engine(self, name: str):
        if name not in ("breeze", "qwen3"):
            return {"ok": False, "error": "unknown engine"}
        config.update({"engine": name})
        self._app.switch_engine_async(name)
        return {"ok": True}

    def download_engine(self, name: str):
        def job():
            self._dl.update(active=True, progress=0.0)
            try:
                cb = lambda p, label: self._dl.update(progress=p, label=label)  # noqa: E731
                if name == "qwen3":
                    if not downloads.vad_ready():
                        downloads.download_vad(cb)
                    downloads.download_qwen3(cb)
                else:
                    downloads.download_vad(cb)
                    downloads.download_punct(cb)
                    downloads.download_breeze(cb)
            except Exception as e:  # noqa: BLE001
                log.exception("download failed")
                self._dl.update(label=f"下載失敗：{e}")
            finally:
                self._dl.update(active=False)

        threading.Thread(target=job, daemon=True).start()
        return {"ok": True}

    def get_download_progress(self):
        return dict(self._dl)

    # ---- 熱詞 ----
    def get_hotwords(self):
        return HOTWORDS_FILE.read_text(encoding="utf-8") if HOTWORDS_FILE.exists() else ""

    def set_hotwords(self, text: str):
        HOTWORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        HOTWORDS_FILE.write_text(text, encoding="utf-8")
        return {"ok": True}

    # ---- 歷史 ----
    def get_history(self, limit: int = 200):
        return self._app.history.list(limit)

    def clear_history(self):
        self._app.history.clear()
        return {"ok": True}

    # ---- 其他 ----
    def set_autostart(self, enabled: bool):
        self._app.set_autostart(enabled)
        config.update({"autostart": enabled})
        return {"ok": True}

    def mic_test_start(self):
        self._app.recorder.start()
        return {"ok": True}

    def mic_test_stop(self):
        audio = self._app.recorder.stop()
        level = float(abs(audio).max()) if len(audio) else 0.0
        return {"ok": True, "level": level, "seconds": len(audio) / 16000}

    def env_check(self):
        try:
            import ctranslate2
            n = ctranslate2.get_cuda_device_count()
            return {"cuda": n > 0, "detail": f"CUDA 裝置數：{n}"}
        except Exception as e:  # noqa: BLE001
            return {"cuda": False, "detail": f"檢查失敗：{e}"}

    def mark_first_run_done(self):
        cfg = config.update({"first_run_done": True})
        # 啟動時模型尚未下載完成會先載入失敗；精靈下載完成後重新載入目前預設引擎。
        self._app.switch_engine_async(cfg["engine"])
        return {"ok": True}
