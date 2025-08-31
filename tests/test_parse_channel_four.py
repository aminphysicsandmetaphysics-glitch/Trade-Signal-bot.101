import pytest
from signal_bot import parse_channel_four

# Valid messages that include entry ranges and multiple SL/TP styles
VALID_SIGNALS = [
    (
        """#XAUUSD\nSell Limit\nEntry Range: 1930 - 1935\nTP1: 1920\nTP2: 1910\nSL: 1940\n""",
        """\
📊 #XAUUSD\n📉 Position: Sell Limit\n❗️ R/R : 1/1\n💲 Entry Price : 1930\n🎯 Entry Range : 1930 – 1935\n✔️ TP1 : 1920\n✔️ TP2 : 1910\n🚫 Stop Loss : 1940""",
    ),
    (
        """#EURUSD\nBuy\nEntry: 1.0800-1.0810\nTake Profit 1 : 1.0850\nTake Profit 2 : 1.0900\nStop Loss : 1.0780\n""",
        """\
📊 #EURUSD\n📉 Position: Buy\n❗️ R/R : 1/2.5\n💲 Entry Price : 1.0800\n🎯 Entry Range : 1.0800 – 1.0810\n✔️ TP1 : 1.0850\n✔️ TP2 : 1.0900\n🚫 Stop Loss : 1.0780""",
    ),
]

# Invalid messages or edge cases
INVALID_SIGNALS = [
    # Missing SL
    """#XAUUSD\nSell\nEntry Range: 1930-1935\nTP1: 1920\nTP2: 1910\n""",
    # Reversed TP direction (buy but TP below entry)
    """#EURUSD\nBuy\nEntry Range: 1.0800-1.0810\nTP1: 1.0700\nTP2: 1.0600\nSL: 1.0750\n""",
]

# Noise messages that should be ignored
NOISE_MESSAGES = [
    "TP reached! Great profits",
    "Move SL to entry",
]


@pytest.mark.parametrize("message,expected", VALID_SIGNALS)
def test_parse_channel_four_valid(message, expected):
    assert parse_channel_four(message, 1234) == expected


@pytest.mark.parametrize("message", INVALID_SIGNALS)
def test_parse_channel_four_invalid(message):
    assert parse_channel_four(message, 1234) is None


@pytest.mark.parametrize("message", NOISE_MESSAGES)
def test_parse_channel_four_noise(message):
    assert parse_channel_four(message, 1234) is None
