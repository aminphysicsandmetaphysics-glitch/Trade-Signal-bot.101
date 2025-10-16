"""Utility helpers for validating parsed trading signals."""
from __future__ import annotations

import re
from typing import Iterable


def _coerce_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def has_valid_name(name: str | None) -> bool:
    """Check that the provided instrument/name token looks like a word."""
    if not isinstance(name, str):
        return False
    return bool(re.search(r"[A-Za-z\u0600-\u06FF]", name.strip()))


def validate_price_structure(
    entry: float | None,
    targets: Iterable[float],
    stop: float | None,
    side: str | None,
) -> bool:
    """Ensure the numeric relationship between entry, targets, and stop is sensible."""
    entry_val = _coerce_float(entry)
    stop_val = _coerce_float(stop)
    if entry_val is None or stop_val is None:
        return False

    cleaned_targets: list[float] = []
    for target in targets:
        target_val = _coerce_float(target)
        if target_val is None:
            return False
        cleaned_targets.append(target_val)

    if not cleaned_targets:
        return False

    side_normalized = (side or "").upper()
    if side_normalized not in {"LONG", "SHORT"}:
        return False

    if side_normalized == "LONG":
        if stop_val >= entry_val:
            return False
        if any(t <= entry_val for t in cleaned_targets):
            return False
    else:
        if stop_val <= entry_val:
            return False
        if any(t >= entry_val for t in cleaned_targets):
            return False

    return True
