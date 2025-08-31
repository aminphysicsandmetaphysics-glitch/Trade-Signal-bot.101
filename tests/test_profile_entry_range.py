import pytest
from signal_bot import parse_signal, parse_channel_four

MESSAGE = """#XAUUSD\nSell Limit\nEntry Range: 1930 - 1935\nTP1: 1920\nTP2: 1910\nSL: 1940\n"""


def test_parse_signal_respects_allow_entry_range_true():
    profile = {"allow_entry_range": True}
    expected = parse_channel_four(MESSAGE, 1234)
    assert parse_signal(MESSAGE, 1234, profile) == expected


def test_parse_signal_rejects_entry_range_when_not_allowed():
    profile = {}
    assert parse_signal(MESSAGE, 1234, profile) is None
  
