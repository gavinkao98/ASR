"""探針冒煙測試：正常行程 heap 完好，checkpoint 不得拋錯、不得誤報。"""
from app import heapprobe


def test_checkpoint_smoke():
    heapprobe.checkpoint("測試站A")
    heapprobe.checkpoint("測試站B")
    assert heapprobe._dirty is False  # 健康行程不得誤報損毀
