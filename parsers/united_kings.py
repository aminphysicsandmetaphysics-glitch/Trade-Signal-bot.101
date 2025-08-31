import re
from typing import Optional, Tuple

ENTRY_RANGE_RE = re.compile(r"@?\s*(-?\d+(?:\.\d+)?)\s*[-\u2010-\u2015]\s*(-?\d+(?:\.\d+)?)")


def parse_united_kings(t: str) -> Tuple[Optional[Tuple[float, float]], Optional[str]]:
    """Extract the entry range from a United Kings style message.

    Parameters
    ----------
    t: str
        Message text possibly containing an entry range.

    Returns
    -------
    Tuple[Optional[Tuple[float, float]], Optional[str]]
        ``((lo, hi), None)`` if a range is found. Otherwise ``(None, "no entry range")``.
    """
    mrange = ENTRY_RANGE_RE.search(t)
    if not mrange:
        return None, "no entry range"
    a = float(mrange.group(1))
    b = float(mrange.group(2))
    lo, hi = sorted((a, b))
    return (lo, hi), None
