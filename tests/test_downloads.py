from app.downloads import pick_asset


def test_pick_asset_by_patterns():
    names = ["Qwen3-ASR-1.7B-q8_0.gguf", "mmproj-Qwen3-ASR-1.7B-f16.gguf",
             "llama-b6000-bin-win-cuda-x64.zip", "source.zip"]
    assert pick_asset(names, ["*q8_0.gguf"]) == "Qwen3-ASR-1.7B-q8_0.gguf"
    assert pick_asset(names, ["mmproj*.gguf"]) == "mmproj-Qwen3-ASR-1.7B-f16.gguf"
    assert pick_asset(names, ["*win-cuda*x64*.zip", "*win-cuda*.zip"]) \
        == "llama-b6000-bin-win-cuda-x64.zip"


def test_pick_asset_none_when_missing():
    assert pick_asset(["a.txt"], ["*.gguf"]) is None
