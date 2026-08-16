import time

from app.ui.bridge import Bridge


class FakeApp:
    def __init__(self):
        self.engine_switches = []
        self.autostart_calls = []

    def switch_engine_async(self, name):
        self.engine_switches.append(name)

    def apply_config_side_effects(self, patch):
        pass

    def set_autostart(self, enabled):
        self.autostart_calls.append(enabled)


def test_set_config_returns_merged(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "c.json")
    b = Bridge(FakeApp())
    out = b.set_config({"sounds_enabled": False})
    assert out["sounds_enabled"] is False


def test_switch_engine_delegates(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "c.json")
    app = FakeApp()
    b = Bridge(app)
    assert b.switch_engine("qwen3")["ok"] is True
    assert app.engine_switches == ["qwen3"]


def test_mark_first_run_done_loads_default_engine(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "c.json")
    app = FakeApp()
    b = Bridge(app)

    assert b.mark_first_run_done() == {"ok": True}
    assert config.load()["first_run_done"] is True
    assert app.engine_switches == ["qwen3"]


def test_env_check_reports_gpu(monkeypatch):
    """env_check 的回傳格式是前端契約：{"cuda": bool, "detail": str}。"""
    from app.ui import bridge as bridge_mod
    monkeypatch.setattr(bridge_mod.gpu, "detect",
                        lambda: {"available": True, "detail": "RTX 4070"})
    assert Bridge(FakeApp()).env_check() == {"cuda": True, "detail": "RTX 4070"}


def test_download_blocked_without_gpu(monkeypatch):
    """沒有 GPU 就不該讓使用者下載 3.6GB 後才在載入引擎時失敗。"""
    from app.ui import bridge as bridge_mod
    monkeypatch.setattr(bridge_mod.gpu, "detect",
                        lambda: {"available": False, "detail": "找不到 NVIDIA 驅動程式"})
    started = []
    monkeypatch.setattr(bridge_mod.downloads, "download_qwen3",
                        lambda cb: started.append("qwen3"))

    b = Bridge(FakeApp())
    res = b.download_engine("qwen3")

    assert res["ok"] is False
    assert started == []               # 完全沒有開始下載
    progress = b.get_download_progress()
    assert progress["active"] is False
    # 前端用 /失敗/ 比對 label 判斷是否失敗（見 web/app.js pollDownload），要對得上
    assert "失敗" in progress["label"]


def test_download_proceeds_with_gpu(monkeypatch):
    from app.ui import bridge as bridge_mod
    monkeypatch.setattr(bridge_mod.gpu, "detect",
                        lambda: {"available": True, "detail": "RTX 4070"})
    started = []
    monkeypatch.setattr(bridge_mod.downloads, "vad_ready", lambda: True)
    monkeypatch.setattr(bridge_mod.downloads, "download_qwen3",
                        lambda cb: started.append("qwen3"))

    b = Bridge(FakeApp())
    assert b.download_engine("qwen3")["ok"] is True
    for _ in range(200):               # 下載跑在背景執行緒
        if started:
            break
        time.sleep(0.01)
    assert started == ["qwen3"]


def test_hotwords_roundtrip(tmp_path, monkeypatch):
    from app.ui import bridge as bridge_mod
    monkeypatch.setattr(bridge_mod, "HOTWORDS_FILE", tmp_path / "hw.txt")
    b = Bridge(FakeApp())
    b.set_hotwords("派森=Python")
    assert b.get_hotwords() == "派森=Python"
