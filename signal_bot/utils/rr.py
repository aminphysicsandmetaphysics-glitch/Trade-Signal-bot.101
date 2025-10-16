def format_rr(entry: float, stop: float, first_tp: float, side: str | None) -> str | None:
    if entry is None or stop is None or first_tp is None:
        return None
    side_u = (side or "").upper()
    if side_u == "SHORT":
        profit = abs(entry - first_tp)
        risk   = abs(stop - entry)
    else:
        profit = abs(first_tp - entry)
        risk   = abs(entry - stop)
    if risk == 0:
        return None
    r = profit / risk
    if r >= 3:
        return f"1/{round(r):d}"
    return f"1/{round(r, 1)}"
