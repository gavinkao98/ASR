import re

import pytest

from app import downloads
from app.downloads import pick_asset, select_llama_assets

# 取自 llama.cpp b9964 的真實 Windows 資產清單。重點在於同一個 release 會同時提供
# CUDA 12.4 與 13.3——這正是「server 與 cudart 版本錯配」的來源。
B9964_ASSETS = [
    "cudart-llama-bin-win-cuda-12.4-x64.zip",
    "cudart-llama-bin-win-cuda-13.3-x64.zip",
    "llama-b9964-bin-win-cpu-arm64.zip",
    "llama-b9964-bin-win-cpu-x64.zip",
    "llama-b9964-bin-win-cuda-12.4-x64.zip",
    "llama-b9964-bin-win-cuda-13.3-x64.zip",
    "llama-b9964-bin-win-hip-radeon-x64.zip",
    "llama-b9964-bin-win-vulkan-x64.zip",
]


def test_llamacpp_tag_is_pinned():
    """llama.cpp 幾乎每天發版且 audio 介面有過破壞性變更；版本必須釘死而非抓 latest。"""
    assert re.fullmatch(r"b\d+", downloads.LLAMACPP_TAG), downloads.LLAMACPP_TAG


def test_select_llama_assets_matches_cuda_versions():
    """server 與 cudart 必須是同一個 CUDA 版本，不可一個 12.4 一個 13.3。"""
    picked = [name for name, _ in select_llama_assets(B9964_ASSETS)]
    assert picked == ["llama-b9964-bin-win-cuda-12.4-x64.zip",
                      "cudart-llama-bin-win-cuda-12.4-x64.zip"]


def test_select_llama_assets_errors_when_cuda_version_gone():
    """上游若拿掉目前釘住的 CUDA 版本，要明確報錯而非默默抓到別版。"""
    without_124 = [n for n in B9964_ASSETS if "12.4" not in n]
    with pytest.raises(RuntimeError, match="12.4"):
        select_llama_assets(without_124)


def test_pick_asset_by_patterns():
    names = ["Qwen3-ASR-1.7B-q8_0.gguf", "mmproj-Qwen3-ASR-1.7B-f16.gguf",
             "llama-b6000-bin-win-cuda-x64.zip", "source.zip"]
    assert pick_asset(names, ["*q8_0.gguf"]) == "Qwen3-ASR-1.7B-q8_0.gguf"
    assert pick_asset(names, ["mmproj*.gguf"]) == "mmproj-Qwen3-ASR-1.7B-f16.gguf"
    assert pick_asset(names, ["*win-cuda*x64*.zip", "*win-cuda*.zip"]) \
        == "llama-b6000-bin-win-cuda-x64.zip"


def test_pick_asset_none_when_missing():
    assert pick_asset(["a.txt"], ["*.gguf"]) is None
