import pytest

from app import downloads
from app.postprocess.punct import add_punct

pytestmark = pytest.mark.skipif(not downloads.punct_ready(), reason="需先下載標點模型")


def test_adds_some_punctuation():
    out = add_punct("今天天氣很好我們去公園散步")
    assert any(p in out for p in "，。？！,.?!")


def test_empty_passthrough():
    assert add_punct("") == ""
