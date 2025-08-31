import pytest
from signal_bot import parse_signal

# Sample United Kings messages
VALID_SIGNALS = [
    (
        """#XAUUSD\nBuy\nEntry Price : 1932\nTP1 : 1935\nTP2 : 1940\nStop Loss : 1925\nRisk Reward 1:3\n""",
        """\
📊 #XAUUSD\n📉 Position: Buy\n❗️ R/R : 1/3\n💲 Entry Price : 1932\n✔️ TP1 : 1935\n✔️ TP2 : 1940\n🚫 Stop Loss : 1925""",
    ),
]

INVALID_SIGNALS = [
    """#XAUUSD\nBuy\nEntry Price: 1932\nStop Loss: 1925""",  # Missing TP
]

NOISE_MESSAGES = [
    "TP reached! Great profits",  # Update/Noise
]


@pytest.mark.parametrize("message,expected", VALID_SIGNALS)
def test_parse_united_kings_valid(message, expected):
    assert parse_signal(message, 1234) == expected


@pytest.mark.parametrize("message", INVALID_SIGNALS)
def test_parse_united_kings_invalid(message):
    assert parse_signal(message, 1234) is None


@pytest.mark.parametrize("message", NOISE_MESSAGES)
def test_parse_united_kings_noise(message):
    assert parse_signal(message, 1234) is None
