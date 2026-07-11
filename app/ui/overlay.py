"""錄音指示浮窗：置頂無邊框小條，顯示「● 錄音中」與音量條。"""
import queue
import threading
import tkinter as tk

_CORNERS = {"top-left": (20, 20), "top-right": (-240, 20),
            "bottom-left": (20, -80), "bottom-right": (-240, -80)}


class Overlay:
    def __init__(self, corner: str = "bottom-right"):
        self._corner = corner
        self._q: queue.Queue = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def show(self) -> None:
        self._q.put(("show", None))

    def hide(self) -> None:
        self._q.put(("hide", None))

    def set_level(self, level: float) -> None:
        self._q.put(("level", min(1.0, level * 3)))

    def set_corner(self, corner: str) -> None:
        self._corner = corner
        self._q.put(("corner", corner))

    def _run(self) -> None:
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg="#1e1e1e")
        root.withdraw()
        tk.Label(root, text="●  錄音中", fg="#ff5555", bg="#1e1e1e",
                 font=("Microsoft JhengHei UI", 11)).pack(padx=12, pady=(6, 0))
        bar = tk.Canvas(root, width=200, height=8, bg="#333333",
                        highlightthickness=0)
        bar.pack(padx=12, pady=(4, 8))
        fill = bar.create_rectangle(0, 0, 0, 8, fill="#4caf50", width=0)

        def place():
            root.update_idletasks()
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            dx, dy = _CORNERS.get(self._corner, _CORNERS["bottom-right"])
            x = dx if dx >= 0 else sw + dx
            y = dy if dy >= 0 else sh + dy
            root.geometry(f"+{x}+{y}")

        def poll():
            try:
                while True:
                    cmd, val = self._q.get_nowait()
                    if cmd == "show":
                        place(); root.deiconify()
                    elif cmd == "hide":
                        root.withdraw()
                    elif cmd == "level":
                        bar.coords(fill, 0, 0, int(200 * val), 8)
                    elif cmd == "corner":
                        place()
            except queue.Empty:
                pass
            root.after(50, poll)

        poll()
        root.mainloop()
