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
    *,
    entry_candidates: Iterable[float] | None = None,
) -> bool:
    """Ensure the numeric relationship between entry, targets, and stop is sensible."""
    stop_val = _coerce_float(stop)
    if stop_val is None:
        return False

    # Normalise entry values.  ``entry`` represents the preferred execution
    # price (for ranges we pick the best value), while ``entry_candidates``
    # contains every quoted level.  Having the full range allows us to enforce
    # that stops/targets make sense for *any* fill within that range.
    normalized_entries: list[float] = []
    if entry_candidates is not None:
        for cand in entry_candidates:
            cand_val = _coerce_float(cand)
            if cand_val is None:
                return False
            normalized_entries.append(cand_val)

    entry_val = _coerce_float(entry)
    if entry_val is None and not normalized_entries:
        return False
    if entry_val is not None:
        normalized_entries.append(entry_val)

    if not normalized_entries:
        return False

    entry_min = min(normalized_entries)
    entry_max = max(normalized_entries)

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
        # Stop must sit beneath the entire entry zone and every target should
        # offer positive distance above the highest quoted entry.
        if stop_val >= entry_min:
            return False
        if any(t <= entry_max for t in cleaned_targets):
            return False
    else:
        # For shorts the stop must be above the entire entry zone while every
        # target should be strictly below the lowest entry quote.
        if stop_val <= entry_max:
            return False
        if any(t >= entry_min for t in cleaned_targets):
            return False

    return True
