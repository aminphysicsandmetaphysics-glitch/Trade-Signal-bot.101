import pytest
from signal_bot import parse_signal

# Sample United Kings messages
VALID_SIGNALS = [
    (
        """#XAUUSD\nBuy\nEntry Price : 1932\nTP1 : 1935\nTP2 : 1940\nStop Loss : 1925\nRisk Reward 1:3\n""",
        """\
📊 #XAUUSD\n📉 Position: Buy\n❗️ R/R : 1/3\n💲 Entry Price : 1932\n✔️ TP1 : 1935\n✔️ TP2 : 1940\n🚫 Stop Loss : 1925""",
    ),
    (
        """#XAUUSD\nBuy\n@1900-1910\nTP1 : 1915\nTP2 : 1920\nSL : 1890\n""",
        """\
📊 #XAUUSD\n📉 Position: Buy\n❗️ R/R : 1.5/1\n💲 Entry Price : 1905\n🎯 Entry Range : 1900 – 1910\n✔️ TP1 : 1915\n✔️ TP2 : 1920\n🚫 Stop Loss : 1890""",
    ),
    (
        """#XAUUSD\nSell\n@1900-1910\nTP1 : 1890\nTP2 : 1880\nSL : 1910\n""",
        """\
📊 #XAUUSD\n📉 Position: Sell\n❗️ R/R : 1/3\n💲 Entry Price : 1905\n🎯 Entry Range : 1900 – 1910\n✔️ TP1 : 1890\n✔️ TP2 : 1880\n🚫 Stop Loss : 1910""",
    ),
]

INVALID_SIGNALS = [
    """#XAUUSD\nBuy\nEntry Price: 1932\nStop Loss: 1925""",  # Missing TP
    # Mixed TP directions (buy with TP below entry)
    """#XAUUSD\nBuy\nEntry Price : 1900\nTP1 : 1910\nTP2 : 1890\nStop Loss : 1895\n""",
    # Mixed TP directions (sell with TP above entry)
    """#XAUUSD\nSell\nEntry Price : 1900\nTP1 : 1890\nTP2 : 1910\nStop Loss : 1915\n""",
    # Range with TP below midpoint for buy
    """#XAUUSD\nBuy\n@1900-1910\nTP1 : 1903\nTP2 : 1915\nSL : 1890\n""",
    # Range with TP above midpoint for sell
    """#XAUUSD\nSell\n@1900-1910\nTP1 : 1912\nTP2 : 1890\nSL : 1915\n""",
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
