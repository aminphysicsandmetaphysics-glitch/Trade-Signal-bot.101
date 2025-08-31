import pytest
from signal_bot import classic_extract_entry


@pytest.mark.parametrize("lines, expected", [
    (["Buy 1.2345 TP 1.2400 SL 1.2320"], "1.2345"),
    (["TP 1.2400 SL 1.2320 Buy 1.2345"], "1.2345"),
    (["Entry Price 1.2345, TP1 1.2400, SL 1.2320"], "1.2345"),
])
def test_classic_extract_entry_mixed_numbers(lines, expected):
    assert classic_extract_entry(lines) == expected
