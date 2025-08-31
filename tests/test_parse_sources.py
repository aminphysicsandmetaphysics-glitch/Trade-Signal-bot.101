import pytest
from signal_bot import (
    parse_gold_exclusive,
    parse_lingrid,
    parse_forex_rr,
    parse_message_by_source,
)


def test_parse_gold_exclusive():
    message = """#XAUUSD\nBuy\nEntry 1900\nSL 1890\nTP 1910\nR/R 1/2\nTF 1H\n"""
    expected = """\
📊 #XAUUSD
📉 Position: Buy
❗️ R/R : 1/2
💲 Entry Price : 1900
✔️ TP1 : 1910
🚫 Stop Loss : 1890
⏳ TF : 1H"""
    result, meta = parse_gold_exclusive(message)
    assert result == expected
    assert meta["symbol"] == "XAUUSD"
    assert meta["position"] == "Buy"
    assert meta["rr"] == "1/2"
    assert meta["tf"] == "1H"


def test_parse_lingrid():
    message = """#EURUSD\nSell\nEntry 1.1000\nSL 1.1050\nTP 1.0950\nR/R 1/2\nTime Frame 1H\n"""
    expected = """\
📊 #EURUSD
📉 Position: Sell
❗️ R/R : 1/2
💲 Entry Price : 1.1000
✔️ TP1 : 1.0950
🚫 Stop Loss : 1.1050
⏳ TF : 1H"""
    result, meta = parse_lingrid(message)
    assert result == expected
    assert meta["symbol"] == "EURUSD"
    assert meta["position"] == "Sell"
    assert meta["tf"] == "1H"


def test_parse_forex_rr():
    message = """#GBPUSD\nBuy\nEntry 1.3000\nSL 1.2950\nTP 1.3100\nR/R 1/2\nTF 30M\n"""
    expected = """\
📊 #GBPUSD
📉 Position: Buy
❗️ R/R : 1/2
💲 Entry Price : 1.3000
✔️ TP1 : 1.3100
🚫 Stop Loss : 1.2950
⏳ TF : 30M"""
    result, meta = parse_forex_rr(message)
    assert result == expected
    assert meta["symbol"] == "GBPUSD"
    assert meta["position"] == "Buy"
    assert meta["tf"] == "30M"


def test_parse_message_by_source_routing():
    msg = "#XAUUSD\nBuy\nEntry 1900\nSL 1890\nTP 1910\nR/R 1/2\nTF 1H\n"
    assert parse_message_by_source(msg, "Gold Exclusive")[0] == parse_gold_exclusive(msg)[0]
    msg2 = "#EURUSD\nSell\nEntry 1.1000\nSL 1.1050\nTP 1.0950\nR/R 1/2\nTF 1H\n"
    assert parse_message_by_source(msg2, "Lingrid")[0] == parse_lingrid(msg2)[0]
    msg3 = "#GBPUSD\nBuy\nEntry 1.3000\nSL 1.2950\nTP 1.3100\nR/R 1/2\nTF 30M\n"
    assert parse_message_by_source(msg3, "Forex RR")[0] == parse_forex_rr(msg3)[0]
    assert parse_message_by_source(msg3, "Unknown") is None
