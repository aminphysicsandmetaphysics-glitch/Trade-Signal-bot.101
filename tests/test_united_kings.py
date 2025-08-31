import signal_bot
import pytest
from signal_bot import (
    parse_signal,
    _looks_like_united_kings,
    _clean_uk_lines,
    UNITED_KINGS_CHAT_IDS,
)

NEW_CHAT_ID = -1002223574325

MESSAGE = """Buy gold @1900-1910
TP1 : 1915
TP2 : 1920
SL : 1890
"""


def test_new_chat_id_present():
    assert NEW_CHAT_ID in UNITED_KINGS_CHAT_IDS


def test_looks_like_united_kings_basic():
    assert _looks_like_united_kings(MESSAGE)


def test_looks_like_united_kings_at_price_synonym():
    msg = "Grab gold @1900\nTP1:1910\nSL:1890"
    assert _looks_like_united_kings(msg)


def _capture(message: str, chat_id: int, monkeypatch):
    captured = {}
    def fake_to_unified(signal, cid, extra):
        captured["signal"] = signal
        captured["extra"] = extra
        return "OK"
    monkeypatch.setattr(signal_bot, "to_unified", fake_to_unified)
    res = parse_signal(message, chat_id, {})
    return res, captured


def test_parse_united_kings_unknown_id_detection(monkeypatch):
    res, cap = _capture(MESSAGE, 1234, monkeypatch)
    assert res == "OK"
    meta = cap["signal"]
    assert meta["symbol"] == "XAUUSD"
    assert meta["position"] == "Buy"
    assert meta["tps"] == ["1915", "1920"]
    assert meta["sl"] == "1890"
    assert cap["extra"]["entries"]["range"] == ["1900", "1910"]


def test_parse_united_kings_known_chat_id(monkeypatch):
    res, cap = _capture(MESSAGE, NEW_CHAT_ID, monkeypatch)
    assert res == "OK"
    meta = cap["signal"]
    assert meta["symbol"] == "XAUUSD"
    assert meta["position"] == "Buy"
    assert meta["tps"] == ["1915", "1920"]
    assert meta["sl"] == "1890"
    assert cap["extra"]["entries"]["range"] == ["1900", "1910"]


@pytest.mark.parametrize(
    "line",
    [
        "TP almost hit",
        "SL hit 1900",
        "SL reached 1900",
        "Breakeven now",
        "Break even achieved",
        "Trade is risk free",
        "Trade is risk    free",
    ],
)
def test_united_kings_noise_lines_ignored(line):
    assert _clean_uk_lines(line) == []
    assert parse_signal(line, NEW_CHAT_ID, {}) is None

