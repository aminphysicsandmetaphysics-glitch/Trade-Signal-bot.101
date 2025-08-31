import pytest
from signal_bot import looks_like_noise_or_update


@pytest.mark.parametrize("message", [
    "Trade Update coming soon",
    "Daily ANALYSIS released",
    "New SETUP forming now",
    "Consider a Partial Close at 50%",
    "TP Reached on EURUSD"
])
def test_noise_keywords(message):
    assert looks_like_noise_or_update(message)
