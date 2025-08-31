import pytest
from signal_bot import parse_signal

NOISY_CLEAN_PAIRS = [
    (
        """Trade Update\n#EURUSD\nBuy\nEntry 1.1000\nSL 1.0950\nTP1 1.1050\n""",
        """#EURUSD\nBuy\nEntry 1.1000\nSL 1.0950\nTP1 1.1050\n""",
    ),
    (
        """Result so far\n#GBPUSD\nSell\nEntry price 1.3000\nSL: 1.3050\nTP1: 1.2900\n""",
        """#GBPUSD\nSell\nEntry price 1.3000\nSL: 1.3050\nTP1: 1.2900\n""",
    ),
    (
        """------------------\nDaily ANALYSIS\n#XAUUSD\nSell\nEntry 1900\nSL 1910\nTP1 1890\n""",
        """#XAUUSD\nSell\nEntry 1900\nSL 1910\nTP1 1890\n""",
    ),
]


@pytest.mark.parametrize("noisy, clean", NOISY_CLEAN_PAIRS)
def test_parse_signal_strips_noise_lines(noisy, clean):
    assert parse_signal(noisy, 1234, {}) == parse_signal(clean, 1234, {})
