import pytest
from signal_bot import parse_signal, CHANNEL_PROFILES


MESSAGE_WITH_RANGE = """#XAUUSD\nSell Limit\nEntry Range: 1930 - 1935\nTP1: 1920\nSL: 1940\n"""

MESSAGE_NO_RANGE = """#BTCUSD\nBuy\nEntry: 100\nTP1: 110\nSL: 90\n"""


def test_flag_hides_entry_price_when_range_present():
    chat_id = 1111
    profile = {"allow_entry_range": True, "show_entry_range_only": True}
    CHANNEL_PROFILES[chat_id] = profile
    result = parse_signal(MESSAGE_WITH_RANGE, chat_id, profile)
    assert "Entry Range" in result
    assert "Entry Price" not in result
    CHANNEL_PROFILES.clear()


def test_without_range_entry_price_shown():
    chat_id = 2222
    profile = {"show_entry_range_only": True}
    CHANNEL_PROFILES[chat_id] = profile
    result = parse_signal(MESSAGE_NO_RANGE, chat_id, profile)
    assert "Entry Price" in result
    CHANNEL_PROFILES.clear()
