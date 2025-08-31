import pytest

from signal_bot import guess_symbol

@pytest.mark.parametrize("text", ["UNITED", "ALRIGHT"])
def test_invalid_words_not_matched(text):
    assert guess_symbol(text) is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("GOLD", "XAUUSD"),
        ("#XAUUSD", "XAUUSD"),
        ("XAU USD", "XAUUSD"),
        ("XAU/USD", "XAUUSD"),
        ("SILVER", "XAGUSD"),
        ("NAS", "NAS100"),
        ("NAS100", "NAS100"),
        ("DJI", "US30"),
        ("DAX", "GER40"),
        ("ETH", "ETHUSDT"),
        ("BTC/USDT", "BTCUSDT"),
    ],
)
def test_symbol_aliases(text, expected):
    assert guess_symbol(text) == expected

