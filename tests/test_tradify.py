from app.postprocess.tradify import to_taiwan


def test_s2twp_vocabulary():
    assert to_taiwan("我用软件看视频") == "我用軟體看影片"


def test_traditional_passthrough():
    assert to_taiwan("已經是繁體的句子") == "已經是繁體的句子"
