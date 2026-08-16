"""NVIDIA GPU 偵測。只用 CUDA driver API，不依賴任何 ML 套件。

原本靠 `ctranslate2.get_cuda_device_count()`，但 ctranslate2 是 **Breeze 引擎**的依賴。
Breeze 降為選用之後它就不保證存在，而 GPU 偵測是**預設引擎 Qwen3** 的前置檢查——
前置檢查不能反過來依賴一個選用元件，否則沒裝 Breeze 的使用者連「有沒有 GPU」都問不出來。

nvcuda.dll 由 NVIDIA 驅動程式安裝。它在不在，正好等同「這台機器能不能跑 CUDA」，
也就是 llama-server 的 CUDA build 能不能啟動——這正是我們要回答的問題。
"""
import ctypes

from app.logger import get_logger

log = get_logger("gpu")

_CUDA_SUCCESS = 0
_NAME_BUF = 256


def _load_cuda():
    """載入 CUDA driver library。抽成獨立函式是為了讓測試能替換掉（見 tests/test_gpu.py）。"""
    return ctypes.WinDLL("nvcuda.dll")


def detect() -> dict:
    """回傳 {"available": bool, "detail": str}。detail 給使用者看，要能自我解釋。"""
    try:
        cuda = _load_cuda()
    except OSError:
        return {"available": False,
                "detail": "找不到 NVIDIA 驅動程式（nvcuda.dll）"}

    try:
        if cuda.cuInit(0) != _CUDA_SUCCESS:
            return {"available": False,
                    "detail": "偵測到 NVIDIA 驅動程式，但 CUDA 初始化失敗（驅動可能需更新）"}

        count = ctypes.c_int()
        if cuda.cuDeviceGetCount(ctypes.byref(count)) != _CUDA_SUCCESS:
            return {"available": False, "detail": "無法查詢 CUDA 裝置數量"}
        if count.value < 1:
            return {"available": False, "detail": "NVIDIA 驅動程式存在，但沒有可用的 CUDA 裝置"}

        names = []
        for i in range(count.value):
            dev = ctypes.c_int()
            if cuda.cuDeviceGet(ctypes.byref(dev), i) != _CUDA_SUCCESS:
                continue
            buf = ctypes.create_string_buffer(_NAME_BUF)
            if cuda.cuDeviceGetName(buf, _NAME_BUF, dev) == _CUDA_SUCCESS:
                names.append(buf.value.decode("utf-8", "replace"))
        return {"available": True,
                "detail": "、".join(names) or f"CUDA 裝置數：{count.value}"}
    except Exception as e:  # noqa: BLE001 - 偵測失敗一律當作「沒有」，不可讓它拖垮精靈
        log.exception("CUDA 偵測發生非預期錯誤")
        return {"available": False, "detail": f"GPU 偵測失敗：{e}"}
