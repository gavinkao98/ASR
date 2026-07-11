import json
import threading

from app.paths import CONFIG_FILE

_LOCK = threading.Lock()

DEFAULTS = {
    "hotkey": "caps lock",
    "hold_threshold_ms": 300,
    "engine": "breeze",              # breeze | qwen3
    "paste_mode": "clipboard",       # clipboard | type
    "use_punct_model": True,          # Breeze 輸出後是否過 ct-punc（Task 21 實測後定案預設）
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
