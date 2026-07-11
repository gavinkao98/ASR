import numpy as np

from app.pipeline import Pipeline


class FakeEngine:
    name = "fake"
    has_punct = True
    outputs_simplified = False

    def transcribe(self, samples, sample_rate=16000):
        return "測試結果"


class FakeManager:
    current = FakeEngine()
    state = "ready"


class FakeRecorder:
    level = 0.0

    def start(self):
        self.started = True

    def stop(self):
        return np.ones(16000, dtype=np.float32)


def make_pipeline(tmp_path, injected, events):
    return Pipeline(
        recorder=FakeRecorder(), engines=FakeManager(),
        vad_fn=lambda s: s,
        chain_factory=lambda eng: (lambda t: t + "！"),
        inject_fn=lambda text, mode: (injected.append(text), True)[1],
        history_add=lambda text, engine: events.append((text, engine)),
        notify=lambda kind: events.append(kind),
        paste_mode="clipboard",
    )


def test_full_flow(tmp_path):
    injected, events = [], []
    p = make_pipeline(tmp_path, injected, events)
    p.on_record_start()
    p.on_record_finish()
    p.join()
    assert injected == ["測試結果！"]
    assert ("測試結果！", "fake") in events


def test_vad_none_cancels(tmp_path):
    injected, events = [], []
    p = make_pipeline(tmp_path, injected, events)
    p._vad_fn = lambda s: None
    p.on_record_start()
    p.on_record_finish()
    p.join()
    assert injected == [] and "empty" in events
