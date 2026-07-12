import json
from app import config


def test_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    cfg = config.load()
    assert cfg["hotkey"] == "caps lock"
    assert cfg["hold_threshold_ms"] == 300
    assert cfg["engine"] == "qwen3"
    assert cfg["paste_mode"] == "clipboard"
    assert cfg["use_punct_model"] is True
    assert cfg["history_enabled"] is True
    assert cfg["verbatim"] is False
    assert cfg["punct_min_chars"] == 10
    assert cfg["digits_to_arabic"] is True
    assert cfg["clipboard_multiformat"] is True  # 已隔離於替身子行程，預設開


def test_save_and_reload_merge(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    config.update({"engine": "qwen3"})
    cfg = config.load()
    assert cfg["engine"] == "qwen3"
    assert cfg["hotkey"] == "caps lock"  # 未設定的鍵保留預設


def test_unknown_keys_preserved(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_FILE", p)
    p.write_text(json.dumps({"future_key": 1}), encoding="utf-8")
    assert config.load()["future_key"] == 1
