"""GPU 偵測測試。全部用假的 CUDA library，所以在沒有顯卡的 CI 上也跑得完整。"""
import ctypes

import pytest

from app import gpu

_OK = 0
_FAIL = 1


class FakeCuda:
    """模擬 nvcuda.dll。ctypes 的 by-reference 輸出參數用 memmove 寫回去。"""

    def __init__(self, *, init=_OK, count=1, count_rc=_OK, names=("NVIDIA GeForce RTX 4070",)):
        self._init, self._count, self._count_rc, self._names = init, count, count_rc, names

    def cuInit(self, flags):  # noqa: N802 - 對應 C API 名稱
        return self._init

    def cuDeviceGetCount(self, ptr):  # noqa: N802
        ctypes.memmove(ptr, ctypes.byref(ctypes.c_int(self._count)),
                       ctypes.sizeof(ctypes.c_int))
        return self._count_rc

    def cuDeviceGet(self, ptr, ordinal):  # noqa: N802
        ctypes.memmove(ptr, ctypes.byref(ctypes.c_int(ordinal)),
                       ctypes.sizeof(ctypes.c_int))
        return _OK

    def cuDeviceGetName(self, buf, size, dev):  # noqa: N802
        # 真正的 DLL 呼叫由 ctypes 代為拆包，假物件收到的是 c_int 本體。
        idx = dev.value if hasattr(dev, "value") else dev
        raw = self._names[idx].encode()[:size - 1] + b"\0"
        ctypes.memmove(buf, raw, len(raw))
        return _OK


@pytest.fixture
def fake_cuda(monkeypatch):
    def install(obj):
        monkeypatch.setattr(gpu, "_load_cuda", lambda: obj)
    return install


def test_no_driver_installed(monkeypatch):
    """最常見的情況：非 NVIDIA 機器，nvcuda.dll 根本不存在。"""
    def boom():
        raise OSError("not found")
    monkeypatch.setattr(gpu, "_load_cuda", boom)
    res = gpu.detect()
    assert res["available"] is False
    assert "nvcuda" in res["detail"]


def test_driver_present_with_device(fake_cuda):
    fake_cuda(FakeCuda())
    res = gpu.detect()
    assert res["available"] is True
    assert "RTX 4070" in res["detail"]


def test_multiple_devices_all_listed(fake_cuda):
    fake_cuda(FakeCuda(count=2, names=("RTX 4070", "RTX 3060")))
    res = gpu.detect()
    assert res["available"] is True
    assert "RTX 4070" in res["detail"] and "RTX 3060" in res["detail"]


def test_driver_present_but_no_devices(fake_cuda):
    """驅動裝了但顯卡被停用/被佔用——不能當成可用。"""
    fake_cuda(FakeCuda(count=0))
    res = gpu.detect()
    assert res["available"] is False


def test_cuinit_failure(fake_cuda):
    fake_cuda(FakeCuda(init=_FAIL))
    res = gpu.detect()
    assert res["available"] is False
    assert "初始化失敗" in res["detail"]


def test_device_count_query_failure(fake_cuda):
    fake_cuda(FakeCuda(count_rc=_FAIL))
    assert gpu.detect()["available"] is False


def test_unexpected_error_is_contained(fake_cuda):
    """偵測本身出意外時要回「沒有」，不能把例外丟出去炸掉精靈。"""
    class Exploding:
        def cuInit(self, flags):  # noqa: N802
            raise RuntimeError("boom")
    fake_cuda(Exploding())
    res = gpu.detect()
    assert res["available"] is False
    assert "boom" in res["detail"]
