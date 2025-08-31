from signal_bot import (
    parse_gold_exclusive,
    parse_lingrid,
    parse_forex_rr,
    parse_message_by_source,
)


def test_parse_gold_exclusive():
    message = """#XAUUSD\nBuy\nEntry 1900\nSL 1890\nTP 1910\nR/R 1/2\nTF 1H\n"""
    _, meta = parse_gold_exclusive(message)
    assert meta["symbol"] == "XAUUSD"
    assert meta["position"] == "Buy"
    assert meta["entry"] == "1900"
    assert meta["sl"] == "1890"
    assert meta["tps"] == ["1910"]
    assert meta["rr"] == "1/2"
    assert meta["tf"] == "1H"
    assert meta.get("notes") == []
    assert meta.get("extra", {}).get("entries", {}).get("range") is None


def test_parse_lingrid():
    message = """#EURUSD\nSell\nEntry 1.1000\nSL 1.1050\nTP 1.0950\nR/R 1/2\nTime Frame 1H\n"""
    _, meta = parse_lingrid(message)
    assert meta["symbol"] == "EURUSD"
    assert meta["position"] == "Sell"
    assert meta["entry"] == "1.1000"
    assert meta["sl"] == "1.1050"
    assert meta["tps"] == ["1.0950"]
    assert meta["rr"] == "1/2"
    assert meta["tf"] == "1H"


def test_parse_forex_rr():
    message = """#GBPUSD\nBuy\nEntry 1.3000\nSL 1.2950\nTP 1.3100\nR/R 1/2\nTF 30M\n"""
    _, meta = parse_forex_rr(message)
    assert meta["symbol"] == "GBPUSD"
    assert meta["position"] == "Buy"
    assert meta["entry"] == "1.3000"
    assert meta["sl"] == "1.2950"
    assert meta["tps"] == ["1.3100"]
    assert meta["rr"] == "1/2"
    assert meta["tf"] == "30M"


def test_parse_message_by_source_routing():
    msg = "#XAUUSD\nBuy\nEntry 1900\nSL 1890\nTP 1910\nR/R 1/2\nTF 1H\n"
    assert parse_message_by_source(msg, "Gold Exclusive")[1] == parse_gold_exclusive(msg)[1]
    msg2 = "#EURUSD\nSell\nEntry 1.1000\nSL 1.1050\nTP 1.0950\nR/R 1/2\nTF 1H\n"
    assert parse_message_by_source(msg2, "Lingrid")[1] == parse_lingrid(msg2)[1]
    msg3 = "#GBPUSD\nBuy\nEntry 1.3000\nSL 1.2950\nTP 1.3100\nR/R 1/2\nTF 30M\n"
    assert parse_message_by_source(msg3, "Forex RR")[1] == parse_forex_rr(msg3)[1]
    assert parse_message_by_source(msg3, "Unknown") is None


def test_parse_gold_exclusive_rejects_updates():
    message = "#XAUUSD\nBuy\nEntry 1900\nSL 1890\nTP reached 1910\n"
    assert parse_gold_exclusive(message) is None


def test_parse_lingrid_direction_validation():
    message = "#EURUSD\nBuy\nEntry 1.1000\nSL 1.0950\nTP 1.0900\n"
    assert parse_lingrid(message) is None

