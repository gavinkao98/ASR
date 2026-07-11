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


def test_hotwords_roundtrip(tmp_path, monkeypatch):
    from app.ui import bridge as bridge_mod
    monkeypatch.setattr(bridge_mod, "HOTWORDS_FILE", tmp_path / "hw.txt")
    b = Bridge(FakeApp())
    b.set_hotwords("派森=Python")
    assert b.get_hotwords() == "派森=Python"
