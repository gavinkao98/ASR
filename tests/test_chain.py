from app.postprocess.chain import build_chain


def fake_punct(text):
    return text + "。"


def test_breeze_like_chain_adds_punct_and_hotwords(tmp_path):
    hw = tmp_path / "hotwords.txt"
    hw.write_text("派森=Python", encoding="utf-8")
    chain = build_chain(has_punct=False, outputs_simplified=False,
                        use_punct_model=True, punct_fn=fake_punct, hotwords_path=hw)
    assert chain("我在學派森") == "我在學Python。"


def test_qwen3_like_chain_tradifies(tmp_path):
    chain = build_chain(has_punct=True, outputs_simplified=True,
                        use_punct_model=True, punct_fn=fake_punct,
                        hotwords_path=tmp_path / "none.txt")
    assert chain("我用软件,很好.") == "我用軟體，很好。"


def test_punct_model_skipped_when_disabled(tmp_path):
    chain = build_chain(has_punct=False, outputs_simplified=False,
                        use_punct_model=False, punct_fn=fake_punct,
                        hotwords_path=tmp_path / "none.txt")
    assert chain("測試") == "測試"
