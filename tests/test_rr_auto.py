import pytest
from signal_bot import parse_signal


def test_parse_signal_calculates_rr():
    message = """#XAUUSD\nBuy\nEntry Price : 1900\nTP1 : 1910\nStop Loss : 1895"""
    expected = (
        "📊 #XAUUSD\n"
        "📉 Position: Buy\n"
        "❗️ R/R : 1/2\n"
        "💲 Entry Price : 1900\n"
        "✔️ TP1 : 1910\n"
        "🚫 Stop Loss : 1895"
    )
    assert parse_signal(message, 1234, {}) == expected
