"""錄音指示浮窗：置頂無邊框圓角膠囊，置於「目前作用中視窗所在螢幕」的正中央，內含隨音量
起伏的對稱聲浪 + 呼吸紅點（無文字）。介面（show/hide/set_level/set_corner）維持不變。
Windows 用 -transparentcolor 去背成圓角膠囊；其他平台後援為純深色方窗。
"""
import ctypes
import math
import queue
import threading
import tkinter as tk

WIN_W, WIN_H = 272, 60
_KEY = "#010101"        # -transparentcolor 去背鍵值色（近黑、不與畫面用色衝突）
_PILL = "#1a1a1f"
_BORDER = "#3a3a44"
_BAR = "#f2a33d"        # 琥珀
_GOLD = "#ffd28a"       # 峰值柔和金（比紅橘更耐看）
_DOT = "#ff5a4d"
_DOT_DIM = "#7a2a25"
_N_BARS = 28

try:
    _user32 = ctypes.windll.user32
    _user32.GetForegroundWindow.restype = ctypes.c_void_p
    _user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    _user32.MonitorFromWindow.restype = ctypes.c_void_p
    _user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _user32.GetMonitorInfoW.restype = ctypes.c_int
except (AttributeError, OSError):   # 非 Windows
    _user32 = None


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", ctypes.c_ulong)]


def _center_xy(win_w: int, win_h: int):
    """算出讓視窗置中於「目前作用中視窗所在螢幕」的左上角座標。多螢幕時會跟著你正在操作的
    那個螢幕跑，而不是只認主螢幕（tkinter 的 winfo_screenwidth 只看得到主螢幕、多螢幕會歪）。
    非 Windows 或失敗回傳 None，呼叫端退回 tkinter 置中。"""
    if _user32 is None:
        return None
    try:
        hmon = _user32.MonitorFromWindow(_user32.GetForegroundWindow(), 2)  # NEAREST
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if not _user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return None
        r = mi.rcMonitor
        return (r.left + (r.right - r.left - win_w) // 2,
                r.top + (r.bottom - r.top - win_h) // 2)
    except Exception:  # noqa: BLE001
        return None


def _lerp(a: str, b: str, t: float) -> str:
    """在兩個 #rrggbb 之間線性內插，供聲浪與紅點做平滑色彩過渡。"""
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return "#%02x%02x%02x" % tuple(
        int(int(a[i:i + 2], 16) + (int(b[i:i + 2], 16) - int(a[i:i + 2], 16)) * t)
        for i in (1, 3, 5)
    )


def _round_rect(cv: tk.Canvas, x0, y0, x1, y1, r, **kw) -> None:
    """用兩個十字矩形 + 四角圓補成圓角矩形（tkinter Canvas 無原生圓角）。"""
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    cv.create_rectangle(x0 + r, y0, x1 - r, y1, outline="", **kw)
    cv.create_rectangle(x0, y0 + r, x1, y1 - r, outline="", **kw)
    for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
        cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline="", **kw)


class Overlay:
    def __init__(self, corner: str = "center"):
        self._corner = corner   # 保留參數相容；位置固定螢幕中央
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
        self._q.put(("place", None))

    def _run(self) -> None:
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-transparentcolor", _KEY)  # Windows：去背成圓角膠囊
            bg = _KEY
        except tk.TclError:                              # 非 Windows 後援：純深色方窗
            bg = _PILL
        root.configure(bg=bg)
        root.withdraw()

        cv = tk.Canvas(root, width=WIN_W, height=WIN_H, bg=bg, highlightthickness=0)
        cv.pack()

        # 靜態底：膠囊外框 + 內填（畫一次）
        _round_rect(cv, 2, 7, WIN_W - 2, WIN_H - 7, 23, fill=_BORDER)
        _round_rect(cv, 3, 8, WIN_W - 3, WIN_H - 8, 22, fill=_PILL)

        cy = WIN_H // 2
        dot = cv.create_oval(20, cy - 4, 28, cy + 4, outline="", fill=_DOT)

        x0, x1 = 42, WIN_W - 14
        pitch = (x1 - x0) / _N_BARS
        env, bars = [], []
        for i in range(_N_BARS):
            u = (i / (_N_BARS - 1)) * 2 - 1
            env.append(0.28 + 0.72 * math.cos(u * 1.28) ** 2)   # 中央高、兩側低的平滑包絡
            bx = x0 + pitch * (i + 0.5)
            bars.append(cv.create_line(bx, cy - 1, bx, cy + 1, width=3,
                                       fill=_BAR, capstyle=tk.ROUND))

        state = {"level": 0.0, "phase": 0.0, "shown": False}

        def place():
            root.update_idletasks()
            xy = _center_xy(WIN_W, WIN_H)
            if xy is None:   # 後援：tkinter 螢幕寬高（僅單螢幕準確）
                xy = ((root.winfo_screenwidth() - WIN_W) // 2,
                      (root.winfo_screenheight() - WIN_H) // 2)
            root.geometry(f"+{xy[0]}+{xy[1]}")

        def draw():
            ph, lv = state["phase"], state["level"]
            for i, item in enumerate(bars):
                wob = 0.5 + 0.5 * math.sin(ph + i * 0.55)       # 流動的波
                h = 3 + env[i] * (0.12 + lv * 0.95) * wob * 32
                bx = x0 + pitch * (i + 0.5)
                cv.coords(item, bx, cy - h / 2, bx, cy + h / 2)
                cv.itemconfig(item, fill=_lerp(_BAR, _GOLD, (h - 8) / 26))
            cv.itemconfig(dot, fill=_lerp(_DOT_DIM, _DOT, 0.5 + 0.5 * math.sin(ph * 0.45)))

        def poll():
            try:
                while True:
                    cmd, val = self._q.get_nowait()
                    if cmd == "show":
                        state["shown"] = True
                        place(); root.deiconify()
                    elif cmd == "hide":
                        state["shown"] = False
                        root.withdraw()
                    elif cmd == "level":
                        state["level"] = val
                    elif cmd == "place":
                        place()
            except queue.Empty:
                pass
            if state["shown"]:
                state["phase"] += 0.22
                draw()
            root.after(50, poll)

        poll()
        root.mainloop()
