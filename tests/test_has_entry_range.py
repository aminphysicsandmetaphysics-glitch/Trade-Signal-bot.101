import pytest
from signal_bot import _has_entry_range


@pytest.mark.parametrize("dash", ["-", "–", "—", "−"])
def test_has_entry_range_accepts_various_dashes(dash):
    text = f"@123{dash}124"
    assert _has_entry_range(text)
