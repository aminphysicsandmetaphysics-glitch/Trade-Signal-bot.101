import pytest
from signal_bot import (
    parse_gold_exclusive,
    parse_lingrid,
    parse_forex_rr,
    parse_message_by_source,
)


def test_parse_gold_exclusive():
    message = """#XAUUSD\nBuy\nEntry 1900\nSL 1890\nTP 1910\nR/R 1/2\nTF 1H\n"""
    signal, reason = parse_gold_exclusive(message)
    assert reason is None
    assert signal["symbol"] == "XAUUSD"
    assert signal["position"] == "Buy"
    assert signal["entry"] == "1900"
    assert signal["sl"] == "1890"
    assert signal["tps"] == ["1910"]
    assert signal["rr"] == "1/2"
    assert signal["tf"] == "1H"


def test_parse_lingrid():
    message = """#EURUSD\nSell\nEntry 1.1000\nSL 1.1050\nTP 1.0950\nR/R 1/2\nTime Frame 1H\n"""
    signal, reason = parse_lingrid(message)
    assert reason is None
    assert signal["symbol"] == "EURUSD"
    assert signal["position"] == "Sell"
    assert signal["entry"] == "1.1000"
    assert signal["sl"] == "1.1050"
    assert signal["tps"] == ["1.0950"]
    assert signal["tf"] == "1H"


def test_parse_forex_rr():
    message = """#GBPUSD\nBuy\nEntry 1.3000\nSL 1.2950\nTP 1.3100\nR/R 1/2\nTF 30M\n"""
    signal, reason = parse_forex_rr(message)
    assert reason is None
    assert signal["symbol"] == "GBPUSD"
    assert signal["position"] == "Buy"
    assert signal["entry"] == "1.3000"
    assert signal["sl"] == "1.2950"
    assert signal["tps"] == ["1.3100"]
    assert signal["tf"] == "30M"


def test_parse_message_by_source_routing():
    msg = "#XAUUSD\nBuy\nEntry 1900\nSL 1890\nTP 1910\nR/R 1/2\nTF 1H\n"
    assert parse_message_by_source(msg, "Gold Exclusive")[0] == parse_gold_exclusive(msg)[0]
    msg2 = "#EURUSD\nSell\nEntry 1.1000\nSL 1.1050\nTP 1.0950\nR/R 1/2\nTF 1H\n"
    assert parse_message_by_source(msg2, "Lingrid")[0] == parse_lingrid(msg2)[0]
    msg3 = "#GBPUSD\nBuy\nEntry 1.3000\nSL 1.2950\nTP 1.3100\nR/R 1/2\nTF 30M\n"
    assert parse_message_by_source(msg3, "Forex RR")[0] == parse_forex_rr(msg3)[0]
    assert parse_message_by_source(msg3, "Unknown") is None
