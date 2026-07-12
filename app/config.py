import json
import threading

from app.paths import CONFIG_FILE

_LOCK = threading.Lock()

DEFAULTS = {
    "hotkey": "caps lock",
    "hold_threshold_ms": 300,
    "engine": "qwen3",               # qwen3 | breeze
    "paste_mode": "clipboard",       # clipboard | type
    "use_punct_model": True,          # Breeze 輸出後是否過 ct-punc（Task 21 實測後定案預設）
    "verbatim": False,                # 原樣輸出：跳過熱詞替換與全形正規化，保留自動標點與簡轉繁
    "punct_min_chars": 10,            # 短句免標點門檻（中文字+英文單字）；低於此不加標點，0=關閉
    "digits_to_arabic": True,         # 中文數字轉阿拉伯：連續數字串逐字＋位值接單位（見 postprocess/digits.py）
    "clipboard_multiformat": False,   # 圖片/檔案還原（暫閉：0xc0000374 排查中，見 inject._multiformat_enabled）
    "force_language": None,           # None=自動偵測；"zh"/"en" 可強制
    "sounds_enabled": True,
    "mic_device": None,               # None=系統預設，否則為裝置名稱字串
    "overlay_corner": "bottom-right",  # 四角：top-left/top-right/bottom-left/bottom-right
    "history_enabled": True,
    "autostart": False,
    "first_run_done": False,
    "qwen3_use_gpu": True,
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    return cfg


def update(patch: dict) -> dict:
    with _LOCK:
        cfg = load()
        cfg.update(patch)
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return cfg
