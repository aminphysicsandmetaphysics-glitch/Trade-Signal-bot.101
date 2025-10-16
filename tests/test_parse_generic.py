from signal_bot.parsers.parse_signal_generic import parse_signal_generic


def test_united_kings_signal():
    msg = """United Kings VIP - Forex, [10/7/2025 9:16 PM]\nUnleash the Gold sell @3983.5-3989.3\n\nSL: 3991.3\n\nTP1: 3981.5\nTP2: 3980\n"""

    parsed = parse_signal_generic(msg)
    assert parsed is not None
    assert not parsed["is_update"]
    assert parsed["symbol"] == "XAUUSD"
    assert parsed["side"] == "SHORT"
    assert parsed["entry"] == 3989.3
    assert parsed["targets"] == [3981.5, 3980.0]
    assert parsed["stop"] == 3991.3


def test_forex_rr_signal():
    msg = """Forex.RR - Premium, [9/30/2025 11:22 AM]\nCHFJPY H2 ✅\n\nSell!\nE: 185.900\nTp: 182.900 ( 300 pips )\nSl: 186.400 ( 50 pips )\nRisk-Reward Ratio:   1 : 6\n"""

    parsed = parse_signal_generic(msg)
    assert parsed is not None
    assert parsed["symbol"] == "CHFJPY"
    assert parsed["side"] == "SHORT"
    assert parsed["entry"] == 185.9
    assert parsed["targets"] == [182.9]
    assert parsed["stop"] == 186.4


def test_lingrid_decimal_comma():
    msg = """Lingrid private signals, [9/17/2025 2:48 PM]\nGOLD BUY 3663,10 ( use small risk 1-2% )\nSL 3647\nTP 3715\n"""

    parsed = parse_signal_generic(msg)
    assert parsed is not None
    assert parsed["symbol"] == "XAUUSD"
    assert parsed["side"] == "LONG"
    assert parsed["entry"] == 3663.1
    assert parsed["targets"] == [3715.0]
    assert parsed["stop"] == 3647.0


def test_gold_exclusive_update_is_detected():
    msg = """GOLD EXCLUSIVE VIP, [8/8/2025 9:34 PM]\n📊 #XAUUSD \n⚜️ VIP SIGNAL\n📆 08.08.2025\n➖➖➖➖➖➖➖➖➖\n✅ TP1 Reached ✅ +30 Pips ✅\n✅ TP2 Reached ✅ +60 Pips ✅\n"""

    parsed = parse_signal_generic(msg)
    assert parsed is not None
    assert parsed["is_update"] is True


def test_signal_without_symbol_is_rejected():
    msg = """VIP Signals\nBuy @ 4030-4028\nTP: 4045\nSL: 4015\n"""

    parsed = parse_signal_generic(msg)
    assert parsed is None


def test_reject_long_with_lower_targets():
    msg = """Lingrid private signals\nGOLD BUY 3663\nSL 3700\nTP 3600\n"""

    parsed = parse_signal_generic(msg)
    assert parsed is None


def test_reject_short_with_higher_targets():
    msg = """United Kings VIP\nSell XAUUSD @ 3983\nSL: 3970\nTP1: 3990\n"""

    parsed = parse_signal_generic(msg)
    assert parsed is None
