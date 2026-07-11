from app.autostart import is_enabled, set_autostart


def test_set_and_remove(monkeypatch):
    import app.autostart as m
    monkeypatch.setattr(m, "APP_KEY_NAME", "ASRVoiceTypingTest")
    try:
        set_autostart(True)
        assert is_enabled() is True
        set_autostart(False)
        assert is_enabled() is False
    finally:
        set_autostart(False)
