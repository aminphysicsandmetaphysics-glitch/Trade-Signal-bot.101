import pytest
from signal_bot import parse_signal, parse_channel_four

MESSAGE = (
    "#XAUUSD\nSell Limit\nEntry: @1930 - 1935\n"
    "Take Profit 1: 1920\nTake Profit 2: 1910\nStop Loss: 1940\n"
)

SINGLE_PRICE_MESSAGE = (
    "#XAUUSD\nSell\nEntry: @1930\nTake Profit 1: 1920\nStop Loss: 1940\n"
)


def test_parse_signal_respects_allow_entry_range_true():
    profile = {"allow_entry_range": True}
    expected = parse_channel_four(MESSAGE, 1234)
    assert parse_signal(MESSAGE, 1234, profile) == expected


def test_parse_signal_rejects_entry_range_when_not_allowed():
    profile = {}
    assert parse_signal(MESSAGE, 1234, profile) is None


def test_parse_signal_accepts_single_price_with_at_prefix():
    profile = {}
    result = parse_signal(SINGLE_PRICE_MESSAGE, 1234, profile)
    assert result is not None
    assert "Entry Range" not in result
  
