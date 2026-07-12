"""剪貼簿替身：常駐子行程，把所有剪貼簿操作隔離出主行程。

背景：主行程內的 API 攔截層（防毒注入）會在 SetClipboardData 呼叫中造成
heap 損毀（0xc0000374）；操作移到替身後，再出事死的是替身，主行程無感、
砍掉重生即可。常駐（而非每次 spawn）是因為冷啟含防毒掃描實測 ~800ms。

用法：pythonw -S -E clipboard_helper.py
協議（stdin/stdout 二進位行，多回合迴圈）：
  stdin  "<mf> <base64(utf-8 文字)>"   mf=0|1 是否多格式快照
  → 快照原剪貼簿（mf=1 白名單多格式；失敗退純文字）→ 寫入新文字
  stdout "READY"
  stdin  "RESTORE" → 還原快照 → stdout "DONE" → 等下一回合
  任何時點 stdin EOF（主行程結束/出錯）：
    ．回合中（已 READY 未 RESTORE）→ 不還原，文字留在剪貼簿（手動 Ctrl+V 退路）
    ．回合間 → 直接結束
"""
import base64
import sys

import clipwin  # 同目錄載入（-S -E 下無 site-packages；clipwin 零依賴）


def _cycle(line: bytes) -> bool:
    """跑一個回合；回傳是否繼續服務。"""
    mf_flag, _, payload = line.strip().partition(b" ")
    text = base64.b64decode(payload).decode("utf-8")

    saved: list[tuple[int, bytes]] | None = None
    old_text: str | None = None
    if mf_flag == b"1":
        try:
            saved = clipwin.snapshot()
        except Exception:  # noqa: BLE001 - 快照出事退回純文字備援
            saved = None
    if saved is None:
        old_text = clipwin.get_text()

    clipwin.set_text(text)
    sys.stdout.buffer.write(b"READY\n")
    sys.stdout.buffer.flush()

    cmd = sys.stdin.buffer.readline().strip()
    if cmd != b"RESTORE":
        return False  # EOF：不還原（文字留給手動貼上），結束服務

    if saved:
        clipwin.restore(saved)
    elif saved is None and old_text is not None:
        clipwin.set_text(old_text)
    # saved == []（原本就是空的）→ 不還原，辨識文字留著
    sys.stdout.buffer.write(b"DONE\n")
    sys.stdout.buffer.flush()
    return True


def main() -> int:
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return 0  # 回合間 EOF：主行程收工
        if not _cycle(line):
            return 0


if __name__ == "__main__":
    sys.exit(main())
