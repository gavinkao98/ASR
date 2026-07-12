"""替身子行程端到端：真 spawn、真剪貼簿、多回合協議與 EOF 語意。"""
import base64
import subprocess
import sys
import threading
import time
from pathlib import Path

from app import clipwin

HELPER = Path(__file__).resolve().parent.parent / "app" / "clipboard_helper.py"


def _read_line(pipe, timeout: float):
    box: list[bytes] = []
    t = threading.Thread(target=lambda: box.append(pipe.readline()), daemon=True)
    t.start()
    t.join(timeout)
    return box[0].strip() if box else None


def _spawn():
    return subprocess.Popen(
        [sys.executable, "-S", "-E", str(HELPER)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _begin(p, text: str, mf: bool = True):
    flag = b"1" if mf else b"0"
    p.stdin.write(flag + b" " + base64.b64encode(text.encode()) + b"\n")
    p.stdin.flush()
    return _read_line(p.stdout, 5.0)


def _finish(p):
    p.stdin.write(b"RESTORE\n")
    p.stdin.flush()
    return _read_line(p.stdout, 5.0)


def test_helper_two_cycles_persistent():
    """常駐：同一隻替身連跑兩回合；第二回合往返必須是毫秒級（<200ms）。"""
    fmt_png = clipwin.register_format("PNG")
    with clipwin.open_clipboard():
        clipwin.empty_clipboard()
        clipwin.write_format_bytes(clipwin.CF_UNICODETEXT, "原有\0".encode("utf-16-le"))
        clipwin.write_format_bytes(fmt_png, b"marker-png")

    p = _spawn()
    try:
        # 回合 1
        assert _begin(p, "替身文字") == b"READY"
        assert clipwin.get_text() == "替身文字"
        assert _finish(p) == b"DONE"
        assert clipwin.get_text() == "原有"          # 多格式還原
        with clipwin.open_clipboard():
            assert clipwin.read_format_bytes(fmt_png) == b"marker-png"
        # 回合 2（暖機後）
        t0 = time.time()
        assert _begin(p, "第二回合") == b"READY"
        warm_ms = (time.time() - t0) * 1000
        print(f"[latency] warm begin→READY = {warm_ms:.0f}ms")
        assert _finish(p) == b"DONE"
        assert warm_ms < 200
        assert clipwin.get_text() == "原有"
    finally:
        p.stdin.close()
        p.wait(timeout=5)


def test_helper_eof_without_restore_leaves_text():
    """主行程出錯沒送 RESTORE（stdin 關閉）→ 不還原，辨識文字留給手動 Ctrl+V。"""
    clipwin.set_text("舊內容")
    p = _spawn()
    assert _begin(p, "留下的文字") == b"READY"
    p.stdin.close()
    assert p.wait(timeout=5) == 0
    assert clipwin.get_text() == "留下的文字"
