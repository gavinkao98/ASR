from app.ptt_logic import PttStateMachine


class Spy:
    def __init__(self):
        self.events = []

    def __call__(self, name):
        return lambda *a: self.events.append(name)


def make(spy, threshold=300):
    return PttStateMachine(
        threshold_ms=threshold,
        on_start=spy("start"), on_finish=spy("finish"),
        on_cancel_tap=spy("cancel_tap"),
    )


def test_long_hold_finishes():
    spy = Spy(); sm = make(spy)
    sm.key_down(t_ms=0)
    sm.key_up(t_ms=500)
    assert spy.events == ["start", "finish"]


def test_short_tap_cancels_and_replays():
    spy = Spy(); sm = make(spy)
    sm.key_down(t_ms=0)
    sm.key_up(t_ms=120)
    assert spy.events == ["start", "cancel_tap"]


def test_autorepeat_keydown_ignored():
    spy = Spy(); sm = make(spy)
    sm.key_down(t_ms=0)
    sm.key_down(t_ms=50)   # Windows 按住會連發 keydown
    sm.key_down(t_ms=100)
    sm.key_up(t_ms=400)
    assert spy.events == ["start", "finish"]
