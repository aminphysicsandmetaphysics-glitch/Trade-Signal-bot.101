from signal_bot import parse_gold_exclusive


def test_hash_symbol_parsed():
    msg = (
        "#XAUUSD\n"
        "Buy now\n"
        "Entry 1900\n"
        "SL 1890\n"
        "TP1: 1910"
    )
    sig, reason = parse_gold_exclusive(msg)
    assert reason is None
    assert sig["symbol"] == "XAUUSD"


def test_hidden_characters():
    msg = (
        "\u200f#X\u200fAUUSD\u200f\n"
        "Buy\u00a0now\n"
        "Entry\u00a01900\n"
        "SL\u00a01890\n"
        "TP1:\u00a01910"
    )
    sig, reason = parse_gold_exclusive(msg)
    assert reason is None
    assert sig["symbol"] == "XAUUSD"
    assert sig["entry"] == "1900"
