import pytest
from signal_bot import parse_signal

# Sample United Kings messages
ENTRY_RANGE_MESSAGE = (
    """#XAUUSD\nSell 1930 - 1935\npips 50 100\nTP1 : 1920\nTP2 : 1910\nSL : 1945\n"""
)
ENTRY_RANGE_EXPECTED = (
    """\
📊 #XAUUSD\n📉 Position: Sell\n❗️ R/R : 1/1\n💲 Entry Price : 1932.5\n🎯 Entry Range : 1930 – 1935\n✔️ TP1 : 1920\n✔️ TP2 : 1910\n🚫 Stop Loss : 1945"""
)

VALID_SIGNALS = [
    (
        """#XAUUSD\nBuy\nEntry Price : 1932\nTP1 : 1935\nTP2 : 1940\nStop Loss : 1925\nRisk Reward 1:3\n""",
        """\
📊 #XAUUSD\n📉 Position: Buy\n❗️ R/R : 1/3\n💲 Entry Price : 1932\n✔️ TP1 : 1935\n✔️ TP2 : 1940\n🚫 Stop Loss : 1925""",
    ),
    (ENTRY_RANGE_MESSAGE, ENTRY_RANGE_EXPECTED),
]

INVALID_SIGNALS = [
    """#XAUUSD\nBuy\nEntry Price: 1932\nStop Loss: 1925""",  # Missing TP
    # Mixed TP directions (buy with TP below entry)
    """#XAUUSD\nBuy\nEntry Price : 1900\nTP1 : 1910\nTP2 : 1890\nStop Loss : 1895\n""",
    # Mixed TP directions (sell with TP above entry)
    """#XAUUSD\nSell\nEntry Price : 1900\nTP1 : 1890\nTP2 : 1910\nStop Loss : 1915\n""",
]

NOISE_MESSAGES = [
    "TP reached! Great profits",  # Update/Noise
]


@pytest.mark.parametrize("message,expected", VALID_SIGNALS)
def test_parse_united_kings_valid(message, expected):
    assert parse_signal(message, 1234, {}) == expected


@pytest.mark.parametrize("message", INVALID_SIGNALS)
def test_parse_united_kings_invalid(message):
    assert parse_signal(message, 1234, {}) is None


@pytest.mark.parametrize("message", NOISE_MESSAGES)
def test_parse_united_kings_noise(message):
    assert parse_signal(message, 1234, {}) is None


def test_parse_united_kings_profile_option():
    profile = {"parser": "united_kings"}
    assert parse_signal(ENTRY_RANGE_MESSAGE, 9999, profile) == ENTRY_RANGE_EXPECTED
