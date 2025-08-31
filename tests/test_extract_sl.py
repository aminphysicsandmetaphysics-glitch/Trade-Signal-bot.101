import pytest
from signal_bot import extract_sl


@pytest.mark.parametrize("lines, expected", [
    (["Buy 1.2345 TP 1.2400 SL 1.2320"], "1.2320"),
    (["Entry Price 1.2345, Stop Loss 1.2320"], "1.2320"),
    (["SL 1.2320 Entry 1.2345"], "1.2320"),
])
def test_extract_sl_entry_and_sl_same_line(lines, expected):
    assert extract_sl(lines) == expected


def test_extract_sl_ignores_sl_without_number():
    lines = ["Buy 1.2345 SL", "TP1 1.2400"]
    assert extract_sl(lines) is None


def test_extract_sl_allows_currency_symbol():
    lines = ["Stop Loss : $3297"]
    assert extract_sl(lines) == "3297"
