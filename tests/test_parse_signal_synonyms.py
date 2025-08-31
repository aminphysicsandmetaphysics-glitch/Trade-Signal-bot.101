import pytest
from signal_bot import parse_signal


@pytest.mark.parametrize("verb", ["purchase", "grab", "long"])
def test_parse_signal_buy_synonyms(verb):
    message = f"#XAUUSD\n{verb}\nEntry Price : 1900\nTP1 : 1910\nStop Loss : 1890"
    result = parse_signal(message, 1234, {})
    assert result and "Position: Buy" in result


@pytest.mark.parametrize("verb", ["offload", "unload", "dump", "short"])
def test_parse_signal_sell_synonyms(verb):
    message = f"#XAUUSD\n{verb}\nEntry Price : 1900\nTP1 : 1890\nStop Loss : 1910"
    result = parse_signal(message, 1234, {})
    assert result and "Position: Sell" in result
