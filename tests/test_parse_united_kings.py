import logging
import pytest
import signal_bot
from signal_bot import parse_signal, parse_signal_united_kings

# Sample United Kings messages
VALID_SIGNALS = [
    (
        """#XAUUSD\nBuy\nEntry Price : 1932\nTP1 : 1935\nTP2 : 1940\nStop Loss : 1925\nRisk Reward 1:3\n""",
        """\
📊 #XAUUSD\n📉 Position: Buy\n❗️ R/R : 1/3\n💲 Entry Price : 1932\n✔️ TP1 : 1935\n✔️ TP2 : 1940\n🚫 Stop Loss : 1925""",
    ),
    (
        """#XAUUSD\nBuy gold\n@1900-1910\nTP1 : 1915\nTP2 : 1920\nSL : 1890\n""",
        """\
📊 #XAUUSD\n📉 Position: Buy\n❗️ R/R : 1/1.5\n💲 Entry Price : 1900.0\n🎯 Entry Range : 1900 – 1910\n✔️ TP1 : 1915\n✔️ TP2 : 1920\n🚫 Stop Loss : 1890""",
    ),
    (
        """#XAUUSD\nSell gold\n@1900-1910\nTP1 : 1890\nTP2 : 1880\nSL : 1910\n""",
        """\
📊 #XAUUSD\n📉 Position: Sell\n❗️ R/R : 1/1\n💲 Entry Price : 1900.0\n🎯 Entry Range : 1900 – 1910\n✔️ TP1 : 1890\n✔️ TP2 : 1880\n🚫 Stop Loss : 1910""",
    ),
]

INVALID_SIGNALS = [
    """#XAUUSD\nBuy\nEntry Price: 1932\nStop Loss: 1925""",  # Missing TP
    # Mixed TP directions (buy with TP below entry)
    """#XAUUSD\nBuy\nEntry Price : 1900\nTP1 : 1910\nTP2 : 1890\nStop Loss : 1895\n""",
    # Mixed TP directions (sell with TP above entry)
    """#XAUUSD\nSell\nEntry Price : 1900\nTP1 : 1890\nTP2 : 1910\nStop Loss : 1915\n""",
    # Range with TP below entry for buy
    """#XAUUSD\nBuy\n@1900-1910\nTP1 : 1895\nTP2 : 1915\nSL : 1890\n""",
    # Range with TP above midpoint for sell
    """#XAUUSD\nSell\n@1900-1910\nTP1 : 1912\nTP2 : 1890\nSL : 1915\n""",
    # Missing position
    """#XAUUSD\n@1900-1910\nTP1 : 1915\nSL : 1890\n""",
    # SL not below entry for buy
    """#XAUUSD\nBuy\nEntry Price : 1900\nTP1 : 1910\nTP2 : 1920\nStop Loss : 1905\n""",
    # SL not above entry for sell
    """#XAUUSD\nSell\nEntry Price : 1900\nTP1 : 1890\nTP2 : 1880\nStop Loss : 1895\n""",
    # Range with TP inside entry range for buy
    """#XAUUSD\nBuy\n@1900-1910\nTP1 : 1905\nTP2 : 1908\nSL : 1890\n""",
    # Range with TP equal to entry for buy
    """#XAUUSD\nBuy gold\n@1900-1910\nTP1 : 1900\nTP2 : 1915\nSL : 1890\n""",
    # Range with SL inside range for buy
    """#XAUUSD\nBuy\n@1900-1910\nTP1 : 1915\nSL : 1905\n""",
    # Range with SL inside range for sell
    """#XAUUSD\nSell\n@1900-1910\nTP1 : 1890\nSL : 1905\n""",
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


def test_parse_united_kings_tp_equal_entry():
    message = """#XAUUSD\nBuy gold\n@1900-1910\nTP1 : 1900\nTP2 : 1915\nSL : 1890\n"""
    assert parse_signal_united_kings(message, 1234) is None


def test_united_kings_entry_range_assignment(monkeypatch):
    captured = {}

    def fake_to_unified(signal, chat_id, extra):
        captured["signal"] = signal
        captured["extra"] = extra
        return "OK"

    monkeypatch.setattr(signal_bot, "to_unified", fake_to_unified)

    message = """#XAUUSD\nBuy\n@1900-1910\nTP1 : 1915\nSL : 1890\n"""
    parse_signal_united_kings(message, 1234)

    assert captured["signal"]["entry"] == "1900.0"
    assert captured["extra"]["entries"]["range"] == ["1900", "1910"]


def test_united_kings_missing_position_logged(caplog):
    message = """#XAUUSD\n@1900-1910\nTP1 : 1915\nSL : 1890\n"""
    with caplog.at_level(logging.INFO):
        assert parse_signal_united_kings(message, 1234) is None
    assert "no position" in caplog.text.lower()
