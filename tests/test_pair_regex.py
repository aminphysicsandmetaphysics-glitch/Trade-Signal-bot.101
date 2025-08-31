import pytest

from signal_bot import guess_symbol, strip_invisibles

@pytest.mark.parametrize("text", ["UNITED", "ALRIGHT"])
def test_invalid_words_not_matched(text):
    assert guess_symbol(text) is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("GOLD", "XAUUSD"),
        ("#XAUUSD", "XAUUSD"),
        ("XAU/USD", "XAUUSD"),
        ("SILVER", "XAGUSD"),
        ("WTI", "USOIL"),
        ("UKOIL", "UKOIL"),
        ("ETH", "ETHUSDT"),
        ("BTC/USDT", "BTCUSDT"),
    ],
)
def test_symbol_aliases(text, expected):
    assert guess_symbol(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("🔥# EURUSD moon", "EURUSD"),
        ("#GBP\u00a0USD", "GBPUSD"),
        ("#EUR\u200fUSD", "EURUSD"),
        ("\u2066🪙#USDJPY🪙\u2069", "USDJPY"),
    ],
)
def test_hashtags_with_emoji_or_invisible(text, expected):
    assert guess_symbol(strip_invisibles(text)) == expected

