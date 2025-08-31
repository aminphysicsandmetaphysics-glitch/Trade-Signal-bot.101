import pytest
from signal_bot import (
    parse_signal_classic,
    parse_channel_four,
    parse_signal_united_kings,
    parse_gold_exclusive,
    parse_lingrid,
    parse_forex_rr,
)


def test_classic_parser_normalizes_symbol():
    msg = "#xau\nBuy\nEntry 1900\nTP1 : 1910\nSL : 1890\n"
    res = parse_signal_classic(msg, 0, return_meta=True)
    assert res is not None
    _, meta = res
    assert meta["symbol"] == "XAUUSD"


def test_channel_four_parser_normalizes_symbol():
    msg = "#xau\nBuy\nEntry @1900-1910\nTP1 : 1915\nSL : 1890\n"
    res = parse_channel_four(msg, 0, return_meta=True)
    assert res is not None
    _, meta = res
    assert meta["symbol"] == "XAUUSD"


def test_united_kings_parser_normalizes_symbol():
    msg = """#xau\nBuy\n@1900-1910\nTP1 : 1915\nTP2 : 1920\nSL : 1890\n"""
    meta, reason = parse_signal_united_kings(msg, 0, return_meta=True)
    assert reason is None
    assert meta["symbol"] == "XAUUSD"


def test_gold_exclusive_parser_normalizes_symbol():
    msg = """Buy Gold now\nEntry 1900\nSL 1890\nTP1: 1910\nR/R 1:2\n"""
    meta, reason = parse_gold_exclusive(msg)
    assert reason is None
    assert meta["symbol"] == "XAUUSD"


def test_lingrid_parser_normalizes_symbol():
    msg = """#xau\nSell now\nEntry 1900\nSL 1910\nTP1: 1890\nR/R 1:2\n"""
    meta, reason = parse_lingrid(msg)
    assert reason is None
    assert meta["symbol"] == "XAUUSD"


def test_forex_rr_parser_normalizes_symbol():
    msg = """OIL BUY\nEntry 80\nSL 78\nTP1: 82\nR/R 1:2\n"""
    meta, reason = parse_forex_rr(msg)
    assert reason is None
    assert meta["symbol"] == "USOIL"
