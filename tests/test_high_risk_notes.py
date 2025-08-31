import pytest
from signal_bot import parse_signal, looks_like_noise_or_update


def test_high_risk_not_noise():
    message = "#XAUUSD\nBuy\nHigh-Risk\nEntry Price : 1900\nTP1 : 1910\nStop Loss : 1890"
    result, meta = parse_signal(message, 1234, {}, return_meta=True)
    assert result is not None
    assert meta["notes"] == ["High-Risk"]


def test_high_risk_keyword_not_flagged():
    assert not looks_like_noise_or_update("High-Risk")
