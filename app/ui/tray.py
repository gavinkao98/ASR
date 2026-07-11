"""系統托盤：暫停/恢復、開啟設定、結束。圖示用 Pillow 現畫（麥克風圓點）。"""
import pystray
from PIL import Image, ImageDraw


def _icon_image(active: bool) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (76, 175, 80, 255) if active else (150, 150, 150, 255)
    d.rounded_rectangle([22, 8, 42, 40], radius=10, fill=color)
    d.arc([14, 20, 50, 52], 0, 180, fill=color, width=4)
    d.line([32, 52, 32, 60], fill=color, width=4)
    return img


class Tray:
    def __init__(self, *, on_toggle_pause, on_open_settings, on_quit):
        self._paused = False
        self._on_toggle_pause = on_toggle_pause
        self._icon = pystray.Icon(
            "asr", _icon_image(True), "語音輸入",
            menu=pystray.Menu(
                pystray.MenuItem(lambda item: "恢復辨識" if self._paused else "暫停辨識",
                                 self._toggle),
                pystray.MenuItem("開啟設定", lambda: on_open_settings()),
                pystray.MenuItem("結束", lambda: (self._icon.stop(), on_quit())),
            ),
        )

    def _toggle(self) -> None:
        self._paused = not self._paused
        self._icon.icon = _icon_image(not self._paused)
        self._on_toggle_pause(self._paused)

    def run_forever(self) -> None:  # 阻塞：給主執行緒收尾用
        self._icon.run()

    def notify(self, msg: str) -> None:
        self._icon.notify(msg, "語音輸入")
