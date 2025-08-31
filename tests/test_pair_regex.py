import pytest

from signal_bot import guess_symbol

@pytest.mark.parametrize("text", ["UNITED", "ALRIGHT"])
def test_invalid_words_not_matched(text):
    assert guess_symbol(text) is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("#XAUUSD", "XAUUSD"),
        ("GOLD", "XAUUSD"),
        ("BTC USDT", "BTCUSDT"),
        ("XAU/USD", "XAUUSD"),
    ],
)
def test_symbol_aliases(text, expected):
    assert guess_symbol(text) == expected

