import re
from signal_bot import (
    parse_gold_exclusive,
    parse_lingrid,
    parse_forex_rr,
    parse_message_by_source,
    parse_signal,
)


def _assert_common(result, symbol, position, entry, tp, sl, rr):
    assert f"#{symbol}" in result
    assert f"Position: {position}" in result
    assert f"Entry Price : {entry}" in result
    assert f"TP1 : {tp}" in result
    assert f"Stop Loss : {sl}" in result
    assert f"R/R : {rr}" in result


def test_parse_gold_exclusive_parses_all_fields():
    message = (
        "Buy Gold now\n"
        "Entry 1900\n"
        "SL 1890\n"
        "TP1: 1910\n"
        "R/R 1:2\n"
        "TF: 15M\n"
        "High Risk"
    )
    result, meta = parse_gold_exclusive(message, return_meta=True)
    _assert_common(result, "XAUUSD", "Buy", "1900", "1910", "1890", "1/2")
    assert "TF: 15M" in result
    assert "High Risk" in result
    assert meta["symbol"] == "XAUUSD"
    assert meta["tf"] == "15M"
    assert meta["high_risk"] is True


def test_parse_lingrid_supports_tf():
    message = (
        "#EURUSD\n"
        "Sell now\n"
        "Entry 1.1000\n"
        "SL 1.1050\n"
        "TP1: 1.0950\n"
        "R/R 1:2\n"
        "TF H1"
    )
    result = parse_lingrid(message)
    _assert_common(result, "EURUSD", "Sell", "1.1000", "1.0950", "1.1050", "1/2")
    assert "TF: H1" in result
    assert "High Risk" not in result


def test_parse_forex_rr_high_risk():
    message = (
        "GBPUSD BUY\n"
        "Entry 1.2000\n"
        "SL 1.1900\n"
        "TP1: 1.2100\n"
        "R/R 1:1\n"
        "TF: 30M\n"
        "High Risk trade"
    )
    result = parse_forex_rr(message)
    _assert_common(result, "GBPUSD", "Buy", "1.2000", "1.2100", "1.1900", "1/1")
    assert "TF: 30M" in result
    assert "High Risk" in result


def test_parse_message_by_source_routes():
    msg = "Buy Gold\nEntry 1900\nSL 1890\nTP 1910\nRR 1:2"
    assert parse_message_by_source(msg, "Gold Exclusive") == parse_gold_exclusive(msg)
    assert parse_message_by_source(msg, "Unknown Channel") is None
