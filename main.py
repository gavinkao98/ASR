"""進入點。務必在 import ctranslate2/faster_whisper 之前先注入 NVIDIA DLL 路徑。"""
import os
import sys
import threading
from pathlib import Path


def _inject_nvidia_dlls() -> None:
    try:
        import nvidia  # noqa: F401
    except ImportError:
        return
    nvidia_root = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for bin_dir in nvidia_root.glob("*/bin"):
        os.add_dll_directory(str(bin_dir))


_inject_nvidia_dlls()


def build_app():
    from app import config, downloads
    from app.audio.recorder import Recorder
    from app.audio.vad import trim_speech
    from app.engines.manager import EngineManager
    from app.history import History
    from app.hotkey import HotkeyListener
    from app.inject import inject_text
    from app.logger import get_logger
    from app.paths import HISTORY_DB, HOTWORDS_FILE, ensure_dirs
    from app.pipeline import Pipeline
    from app.postprocess.chain import build_chain
    from app.postprocess.punct import add_punct
    from app.ui.overlay import Overlay
    from app.ui.sounds import play
    from app.ui.tray import Tray

    ensure_dirs()
    log = get_logger("main")
    cfg = config.load()

    def breeze_factory():
        from app.engines.breeze import BreezeEngine
        return BreezeEngine(force_language=cfg.get("force_language"))

    def qwen3_factory():
        from app.engines.qwen3 import Qwen3Engine
        return Qwen3Engine(use_gpu=cfg.get("qwen3_use_gpu", True))

    engines = EngineManager({"breeze": breeze_factory, "qwen3": qwen3_factory})
    history = History(HISTORY_DB)
    overlay = Overlay(cfg["overlay_corner"])
    recorder = Recorder(cfg.get("mic_device"))

    def chain_factory(engine):
        c = config.load()
        return build_chain(
            has_punct=engine.has_punct,
            outputs_simplified=engine.outputs_simplified,
            use_punct_model=c["use_punct_model"],
            punct_fn=add_punct, hotwords_path=HOTWORDS_FILE,
        )

    def notify(kind: str) -> None:
        c = config.load()
        overlay.hide()
        play({"start": "start", "done": "done",
              "empty": "empty", "error": "error", "busy": "error"}.get(kind, "empty"),
             enabled=c["sounds_enabled"])
        if kind == "start":
            overlay.show()
        elif kind == "error":
            tray.notify("處理失敗：若辨識已完成，文字保留在剪貼簿，可手動 Ctrl+V（詳見 log）")

    def history_add(text: str, engine: str) -> None:
        if config.load()["history_enabled"]:
            history.add(text, engine)

    pipeline = Pipeline(
        recorder=recorder, engines=engines, vad_fn=trim_speech,
        chain_factory=chain_factory, inject_fn=inject_text,
        history_add=history_add, notify=notify,
        paste_mode=cfg["paste_mode"],
    )

    def level_pump():
        import time
        while True:
            if pipeline.recording:
                overlay.set_level(recorder.level)
            time.sleep(0.1)

    threading.Thread(target=level_pump, daemon=True).start()

    listener = HotkeyListener(
        cfg["hotkey"], cfg["hold_threshold_ms"],
        on_start=pipeline.on_record_start,
        on_finish=pipeline.on_record_finish,
    )
    orig_cancel = listener._sm._on_cancel_tap

    def cancel_tap():
        pipeline.on_record_cancel()
        overlay.hide()
        orig_cancel()

    listener._sm._on_cancel_tap = cancel_tap

    def on_toggle_pause(paused: bool) -> None:
        (listener.stop if paused else listener.start)()

    def on_open_settings() -> None:
        log.info("settings window: Task 24 接上")

    def on_quit() -> None:
        listener.stop()
        os._exit(0)  # 常駐執行緒眾多，直接退出最乾淨

    tray = Tray(on_toggle_pause=on_toggle_pause,
                on_open_settings=on_open_settings, on_quit=on_quit)

    def boot():
        try:
            engines.switch(cfg["engine"])   # 背景載入（10 秒級）
            tray.notify(f"引擎 {cfg['engine']} 就緒，按住 {cfg['hotkey']} 說話")
        except Exception as e:  # noqa: BLE001 - CUDA/模型損毀等
            log.exception("engine boot failed")
            tray.notify(f"引擎載入失敗：{e}。請開設定視窗切換引擎，或查看 log")
        listener.start()  # 即使引擎失敗也啟動熱鍵，讓使用者得到「忙碌」回饋而非無聲

    threading.Thread(target=boot, daemon=True).start()
    return tray


if __name__ == "__main__":
    build_app().run_forever()
