from app.postprocess.repeat_guard import looks_repetitive


def test_normal_text_ok():
    assert not looks_repetitive("今天天氣很好，我們去公園散步。")


def test_catches_phrase_loop():
    assert looks_repetitive("好的好的好的好的好的好的好的好的")


def test_catches_long_span_loop():
    assert looks_repetitive("我要去上班我要去上班我要去上班我要去上班")


def test_short_legit_reduplication_ok():
    assert not looks_repetitive("謝謝謝謝")  # 口語疊詞不該誤殺
