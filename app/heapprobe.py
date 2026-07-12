"""Heap 健檢探針（0xc0000374 排查用，結案後整檔移除）。
管線各階段呼叫 checkpoint(stage)：每站 INFO 記錄 heap 是否完好；首次發現損毀記
ERROR 後閉嘴。崩潰後看 asr.log 末尾＝這一輪走到哪站時 heap 還是乾淨的，
與 crash.log（faulthandler）夾出播毒的確切區間。"""
import ctypes

from app.logger import get_logger

log = get_logger("heapprobe")

_k32 = ctypes.windll.kernel32
_k32.GetProcessHeap.restype = ctypes.c_void_p
_k32.HeapValidate.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p]
_heap = _k32.GetProcessHeap()
_dirty = False


def checkpoint(stage: str) -> None:
    global _dirty
    if _dirty:
        return
    if _k32.HeapValidate(_heap, 0, None):
        log.info("heap ok @ %s", stage)
    else:
        _dirty = True
        log.error("HEAP 損毀！首次偵測於「%s」", stage)
