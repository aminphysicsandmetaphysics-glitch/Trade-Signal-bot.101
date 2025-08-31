import pytest

from signal_bot import guess_symbol

@pytest.mark.parametrize("text", ["UNITED", "ALRIGHT"])
def test_invalid_words_not_matched(text):
    assert guess_symbol(text) is None

