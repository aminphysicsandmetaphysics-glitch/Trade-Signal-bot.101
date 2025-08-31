from signal_bot import parse_signal, _looks_like_united_kings, UNITED_KINGS_CHAT_IDS

NEW_CHAT_ID = -1001234567890

MESSAGE = """GOLD
Buy
@1900-1910
TP1 : 1915
TP2 : 1920
SL : 1890
"""

EXPECTED = """\
📊 #XAUUSD
📉 Position: Buy
❗️ R/R : 1/1.5
💲 Entry Price : 1900.0
🎯 Entry Range : 1900.0 – 1910.0
✔️ TP1 : 1915
✔️ TP2 : 1920
🚫 Stop Loss : 1890"""


def test_new_chat_id_present():
    assert NEW_CHAT_ID in UNITED_KINGS_CHAT_IDS


def test_looks_like_united_kings_without_at():
    assert _looks_like_united_kings(MESSAGE)


def test_parse_united_kings_unknown_id_detection():
    assert parse_signal(MESSAGE, 1234, {}) == EXPECTED


def test_parse_united_kings_known_chat_id():
    assert parse_signal(MESSAGE, NEW_CHAT_ID, {}) == EXPECTED
