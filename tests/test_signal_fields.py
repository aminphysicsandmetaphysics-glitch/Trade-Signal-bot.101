import pytest
from signal_bot import parse_signal

def test_parse_signal_includes_required_fields():
    message = "#XAUUSD\nBuy\nEntry Price : 1932\nTP1 : 1935\nSL : 1925\n"
    result = parse_signal(message, 1234, return_meta=True)
    assert result is not None
    text, meta = result
    assert meta["source"] is None
    assert meta["tf"] is None
    assert meta["entry_range"] is None
    assert meta["notes"] == []

def test_parse_signal_entry_range_fields():
    profile = {"allow_entry_range": True}
    message = "#XAUUSD\nBuy\nEntry: @1900-1910\nTP1: 1915\nTP2: 1920\nSL: 1890\n"
    result = parse_signal(message, 1234, profile, return_meta=True)
    assert result is not None
    text, meta = result
    assert meta["entry_range"] == ["1900", "1910"]
    assert meta["source"] is None
    assert meta["tf"] is None
    assert meta["notes"] == []
