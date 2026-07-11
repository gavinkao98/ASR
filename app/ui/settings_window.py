"""設定視窗生命週期。pywebview 視窗須在主執行緒 start；用單例避免重複開。"""
import webview

from app.paths import WEB_DIR


class SettingsWindow:
    def __init__(self, bridge):
        self._bridge = bridge
        self._window = None

    def open(self) -> None:
        if self._window is not None:
            try:
                self._window.show()
                self._window.on_top = True
                self._window.on_top = False
                return
            except Exception:  # noqa: BLE001 - 視窗已被關閉銷毀
                self._window = None
        self._window = webview.create_window(
            "語音輸入設定", url=str(WEB_DIR / "index.html"),
            js_api=self._bridge, width=880, height=640, min_size=(760, 520),
        )
        self._window.events.closed += lambda: setattr(self, "_window", None)
