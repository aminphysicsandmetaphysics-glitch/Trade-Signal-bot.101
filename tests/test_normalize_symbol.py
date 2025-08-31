from signal_bot import normalize_symbol


def test_normalize_symbol_xau():
    assert normalize_symbol("XAU") == "XAUUSD"
