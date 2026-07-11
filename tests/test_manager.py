from app.engines.base import Engine
from app.engines.manager import EngineManager


class FakeEngine(Engine):
    has_punct = False
    outputs_simplified = False

    def __init__(self, name):
        self.name = name
        self.loaded = False

    def load(self):
        self.loaded = True

    def unload(self):
        self.loaded = False

    def transcribe(self, samples, sample_rate=16000):
        return f"[{self.name}]"


def test_switch_unloads_previous():
    a, b = FakeEngine("a"), FakeEngine("b")
    mgr = EngineManager({"a": lambda: a, "b": lambda: b})
    mgr.switch("a")
    assert a.loaded and mgr.current.name == "a"
    mgr.switch("b")
    assert not a.loaded and b.loaded and mgr.current.name == "b"


def test_switch_same_engine_noop():
    a = FakeEngine("a")
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return a
    mgr = EngineManager({"a": factory})
    mgr.switch("a")
    mgr.switch("a")
    assert calls["n"] == 1


def test_state_reporting():
    mgr = EngineManager({"a": lambda: FakeEngine("a")})
    assert mgr.state == "idle"
    mgr.switch("a")
    assert mgr.state == "ready"


def test_transcribe_returns_engine_and_text():
    a = FakeEngine("a")
    mgr = EngineManager({"a": lambda: a})
    mgr.switch("a")
    eng, text = mgr.transcribe(None)
    assert eng is a and text == "[a]"
