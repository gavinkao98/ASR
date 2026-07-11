"""進入點。務必在 import ctranslate2/faster_whisper 之前先注入 NVIDIA DLL 路徑。"""
import os
import sys
import threading
from pathlib import Path


def _inject_nvidia_dlls() -> None:
    """把 pip 安裝的 cuBLAS/cuDNN DLL 目錄加進搜尋路徑（Windows 專用）。
    add_dll_directory 讓 CTranslate2 直接載入的 DLL 找得到；但 cuDNN 8 主 DLL 會用
    「裸檔名 LoadLibrary」載入它的子模組（cudnn_ops_infer64_8.dll 等），那條路徑走的是
    標準搜尋順序、不含 add_dll_directory 的目錄——所以同時把目錄前置到 PATH，兩邊都補。"""
    try:
        import nvidia  # noqa: F401
    except ImportError:
        return
    nvidia_root = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for bin_dir in nvidia_root.glob("*/bin"):
        os.add_dll_directory(str(bin_dir))
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]


_inject_nvidia_dlls()


class App:
    """組裝所有子系統。公開屬性/方法給 Bridge（Task 22）與 pywebview 進入點用：
    engines / pipeline / recorder / history 供 Bridge 讀取；switch_engine_async /
    apply_config_side_effects / set_autostart 供 Bridge 呼叫。"""

    def __init__(self):
        from app import config
        from app.audio.recorder import Recorder
        from app.audio.vad import trim_speech
        from app.engines.manager import EngineManager
        from app.history import History
        from app.inject import inject_text
        from app.logger import get_logger
        from app.paths import HISTORY_DB, HOTWORDS_FILE, ensure_dirs
        from app.pipeline import Pipeline
        from app.postprocess.chain import build_chain
        from app.postprocess.punct import add_punct
        from app.ui.bridge import Bridge
        from app.ui.overlay import Overlay
        from app.ui.settings_window import SettingsWindow
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

        self.engines = EngineManager({"breeze": breeze_factory, "qwen3": qwen3_factory})
        self.history = History(HISTORY_DB)
        self.overlay = Overlay(cfg["overlay_corner"])
        self.recorder = Recorder(cfg.get("mic_device"))

        def chain_factory(engine):
            c = config.load()
            return build_chain(
                has_punct=engine.has_punct,
                outputs_simplified=engine.outputs_simplified,
                use_punct_model=c["use_punct_model"],
                punct_fn=add_punct, hotwords_path=HOTWORDS_FILE,
                verbatim=c.get("verbatim", False),
                punct_min_chars=c.get("punct_min_chars", 10),
            )

        def notify(kind: str) -> None:
            c = config.load()
            self.overlay.hide()
            play({"start": "start", "done": "done",
                  "empty": "empty", "error": "error", "busy": "error"}.get(kind, "empty"),
                 enabled=c["sounds_enabled"])
            if kind == "start":
                self.overlay.show()
            elif kind == "error":
                self.tray.notify("處理失敗：若辨識已完成，文字保留在剪貼簿，可手動 Ctrl+V（詳見 log）")

        def history_add(text: str, engine: str) -> None:
            if config.load()["history_enabled"]:
                self.history.add(text, engine)

        self.pipeline = Pipeline(
            recorder=self.recorder, engines=self.engines, vad_fn=trim_speech,
            chain_factory=chain_factory, inject_fn=inject_text,
            history_add=history_add, notify=notify,
            paste_mode=cfg["paste_mode"],
        )

        def level_pump():
            import time
            while True:
                if self.pipeline.recording:
                    self.overlay.set_level(self.recorder.level)
                time.sleep(0.1)

        threading.Thread(target=level_pump, daemon=True).start()

        def on_hold() -> None:
            # 只有確認長按、且真的在錄音（引擎就緒、麥克風有開）時才給提示音+浮窗
            if self.pipeline.recording:
                notify("start")

        self._on_hold = on_hold

        self.listener = self._make_listener(cfg)

        def on_toggle_pause(paused: bool) -> None:
            (self.listener.stop if paused else self.listener.start)()

        # bridge/settings 須在 tray 之前建立：tray 的 on_open_settings 會呼叫
        # self.on_open_settings -> self.settings.open()。
        self.bridge = Bridge(self)
        self.settings = SettingsWindow(self.bridge)

        def on_quit() -> None:
            self.listener.stop()
            try:
                if self.engines.current is not None:
                    self.engines.current.unload()  # 釋放顯卡 / 關掉 Qwen3 子行程
            except Exception:  # noqa: BLE001
                log.exception("engine unload on quit failed")
            os._exit(0)  # 常駐執行緒眾多，直接退出最乾淨

        self.tray = Tray(on_toggle_pause=on_toggle_pause,
                          on_open_settings=self.on_open_settings, on_quit=on_quit)

        def boot():
            try:
                self.engines.switch(cfg["engine"])   # 背景載入（10 秒級）
                self.tray.notify(f"引擎 {cfg['engine']} 就緒，按住 {cfg['hotkey']} 說話")
            except Exception as e:  # noqa: BLE001 - CUDA/模型損毀等
                log.exception("engine boot failed")
                self.tray.notify(f"引擎載入失敗：{e}。請開設定視窗切換引擎，或查看 log")
            self.listener.start()  # 即使引擎失敗也啟動熱鍵，讓使用者得到「忙碌」回饋而非無聲

        threading.Thread(target=boot, daemon=True).start()

    # ---- 熱鍵監聽器建構（開機用一次、改熱鍵設定時重建一次）----
    def _make_listener(self, cfg):
        from app.hotkey import HotkeyListener

        def on_finish():
            # 放開就立刻收浮窗：聲浪只代表「錄音中」，辨識在背景默默進行。就算辨識較久、
            # 甚至引擎卡住，浮窗也不會賴著不走（先前「用幾次後聲浪停不下來」多半是卡在這）。
            self.overlay.hide()
            self.pipeline.on_record_finish()

        listener = HotkeyListener(
            cfg["hotkey"], cfg["hold_threshold_ms"],
            on_start=self.pipeline.on_record_start,
            on_finish=on_finish,
            on_hold=self._on_hold,   # 確認長按才給提示音/浮窗
        )
        # 短按取消：換掉狀態機的 cancel 回呼，同時補送原鍵
        orig_cancel = listener._sm._on_cancel_tap

        def cancel_tap():
            self.pipeline.on_record_cancel()
            self.overlay.hide()
            orig_cancel()

        listener._sm._on_cancel_tap = cancel_tap
        return listener

    # ---- 供 Tray 呼叫 ----
    def on_open_settings(self) -> None:
        self.settings.open()

    # ---- 供 Bridge（app/ui/bridge.py）呼叫 ----
    def switch_engine_async(self, name: str) -> None:
        threading.Thread(target=lambda: self.engines.switch(name), daemon=True).start()

    def apply_config_side_effects(self, patch: dict) -> None:
        from app import config
        from app.audio.recorder import Recorder
        cfg = config.load()
        if "hotkey" in patch or "hold_threshold_ms" in patch:
            self.listener.stop()
            self.listener = self._make_listener(cfg)
            self.listener.start()
        if "overlay_corner" in patch:
            self.overlay.set_corner(cfg["overlay_corner"])
        if "mic_device" in patch:
            self.recorder = Recorder(cfg["mic_device"])
            self.pipeline._recorder = self.recorder
        if "paste_mode" in patch:
            self.pipeline.paste_mode = cfg["paste_mode"]

    def set_autostart(self, enabled: bool) -> None:
        # app.autostart 是 Task 25 的產物，此刻可能還不存在；只在真正呼叫時才 import，
        # 這樣 `import main`（見 tests/conftest.py）不會因為模組缺失而炸掉。
        from app.autostart import set_autostart
        set_autostart(enabled)


if __name__ == "__main__":
    import webview

    from app import config

    app = App()
    # pystray 的 run_forever() 會阻塞，但 webview.start() 必須佔用主執行緒（pywebview
    # 限制：只能在主執行緒呼叫），所以托盤改丟到背景執行緒常駐。
    threading.Thread(target=app.tray.run_forever, daemon=True).start()

    # --- pywebview 主執行緒生命週期 ---
    # 本任務禁止實跑（見任務限制），以下是讀 pywebview 6.2.1 原始碼
    # （webview/__init__.py、webview/platforms/winforms.py）推導出的結論，
    # 尚未經實際執行驗證，行為仍待使用者有空時手動跑一次確認：
    #   1) webview.start() 呼叫前 windows 清單不可為空，否則丟 WebViewException。
    #   2) 每次「最後一扇視窗」被關閉時（winforms.py on_close：
    #      len(BrowserView.instances) == 0），pywebview 會呼叫 Application.Exit()
    #      讓 webview.start() 直接返回；本程式其餘執行緒都是 daemon，一旦主執行緒
    #      跑出 webview.start() 就會整支程式跟著結束。
    # 若只掛「設定視窗」一扇窗，使用者把它關掉就會誤觸第 2 點、整支程式跟著退出，
    # 違反「關閉設定視窗不能結束程式」的需求。因此另外建一扇永遠隱藏、永不關閉的
    # 哨兵視窗頂著（一定是先建立、成為 uid='master'），讓設定視窗只是附屬（child）
    # 視窗：使用者關掉設定視窗時哨兵仍在，訊息迴圈不會被關掉；之後 SettingsWindow.open()
    # 不論從主執行緒（首次精靈）或托盤背景執行緒（之後任何時候）呼叫都會動態建立/
    # 顯示新的子視窗（pywebview 內部用 WinForms Invoke() 做跨執行緒安全處理）。
    webview.create_window("asr-voice-input-sentinel", html="<html></html>", hidden=True)

    if not config.load()["first_run_done"]:
        app.settings.open()  # 首次執行：自動開設定視窗（精靈）

    webview.start()  # 阻塞主執行緒；哨兵視窗撐住訊息迴圈，之後可用托盤隨時開/關設定
