from signal_bot import (
    parse_gold_exclusive,
    parse_lingrid,
    parse_forex_rr,
    parse_message_by_source,
    parse_signal_united_kings,
)


def _assert_common(sig, symbol, position, entry, tp, sl, rr):
    assert sig["symbol"] == symbol
    assert sig["position"] == position
    assert sig["entry"] == entry
    assert sig["tps"][0] == tp
    assert sig["sl"] == sl
    assert sig["rr"] == rr


def test_parse_gold_exclusive_success():
    message = (
        "Buy Gold now\n"
        "Entry 1900\n"
        "SL 1890\n"
        "TP1: 1910\n"
        "R/R 1:2\n"
        "TF: 15M\n"
        "High Risk"
    )
    sig, reason = parse_gold_exclusive(message)
    assert reason is None
    _assert_common(sig, "XAUUSD", "Buy", "1900", "1910", "1890", "1/2")
    assert sig["tf"] == "15M"
    assert sig["high_risk"] is True


def test_parse_gold_exclusive_failure():
    message = "Buy Gold now\nSL 1890\nTP1: 1910"
    sig, reason = parse_gold_exclusive(message)
    assert sig is None
    assert reason


def test_parse_lingrid_success():
    message = (
        "#EURUSD\n"
        "Sell now\n"
        "Entry 1.1000\n"
        "SL 1.1050\n"
        "TP1: 1.0950\n"
        "R/R 1:2\n"
        "TF H1"
    )
    sig, reason = parse_lingrid(message)
    assert reason is None
    _assert_common(sig, "EURUSD", "Sell", "1.1000", "1.0950", "1.1050", "1/2")
    assert sig["tf"] == "H1"
    assert "high_risk" not in sig


def test_parse_lingrid_failure():
    message = "#EURUSD\nSell now\nEntry 1.1000\nSL 1.1050"
    sig, reason = parse_lingrid(message)
    assert sig is None
    assert reason


def test_parse_forex_rr_success():
    message = (
        "GBPUSD BUY\n"
        "Entry 1.2000\n"
        "SL 1.1900\n"
        "TP1: 1.2100\n"
        "R/R 1:1\n"
        "TF: 30M\n"
        "High Risk trade"
    )
    sig, reason = parse_forex_rr(message)
    assert reason is None
    _assert_common(sig, "GBPUSD", "Buy", "1.2000", "1.2100", "1.1900", "1/1")
    assert sig["tf"] == "30M"
    assert sig["high_risk"] is True


def test_parse_forex_rr_failure():
    message = "GBPUSD BUY\nEntry 1.2000\nTP1 1.2100\nR/R 1:1"
    sig, reason = parse_forex_rr(message)
    assert sig is None
    assert reason


def test_parse_message_by_source_routes():
    msg = "Buy Gold\nEntry ۱۹۰۰\nSL ۱۸۹۰\nTP ۱۹۱۰\nRR ۱:۲\nactivated"
    sig1, r1 = parse_message_by_source(msg, "Gold Exclusive")
    sig2, r2 = parse_gold_exclusive(msg)
    assert sig1 == sig2 and r1 is None and r2 is None
    sig3, r3 = parse_message_by_source(msg, "Unknown Channel")
    assert sig3 == sig2 and r3 is None


def test_parse_message_by_source_gold_keyword_priority():
    msg = (
        "Buy Gold now\n"
        "Entry 1900\n"
        "SL 1890\n"
        "TP1: 1910\n"
        "R/R 1:2\n"
    )
    sig1, r1 = parse_message_by_source(msg, "United Kings VIP")
    sig2, r2 = parse_gold_exclusive(msg)
    assert sig1 == sig2 and r1 is None and r2 is None


def test_parse_message_by_source_united_kings_vip_only():
    msg = (
        "#XAUUSD\n"
        "Buy\n"
        "@1900-1910\n"
        "TP1 : 1915\n"
        "TP2 : 1920\n"
        "SL : 1890\n"
    )
    sig1, r1 = parse_message_by_source(msg, "United Kings VIP")
    sig2, r2 = parse_signal_united_kings(msg, 0, return_meta=True)
    assert sig1 == sig2 and r1 is None and r2 is None
    sig3, r3 = parse_message_by_source(msg, "United Kings Free")
    assert sig3 is None and r3 == "unknown source"
