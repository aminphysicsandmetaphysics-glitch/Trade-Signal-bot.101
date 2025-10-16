import re
from ..utils.normalize import fa_to_en, ensure_usdt
from ..utils.rr import format_rr
from ..utils.numbers import extract_numbers

UPDATE_PATTERNS = [
    r"تارگت\s+(اول|دوم|سوم|چهارم|پنجم)|فول\s*تارگت",
    r"استاپ\s+بیاد\s+نقطه\s+ورود",
    r"کلوز\s*کنید",
    r"در\s+نقطه\s+ورود\s+.*کلوز",
    r"❌-\d+(\.\d+)?\s*%",
    r"✅\+\d+(\.\d+)?\s*%",
    r"این\s+معامله\s+اردر\s+پر\s+نکرده",
]

def is_update_message(text: str) -> bool:
    t = fa_to_en(text or "")
    for pat in UPDATE_PATTERNS:
        if re.search(pat, t, flags=re.I):
            return True
    return False

def pick_best_entry(entries: list[float], side: str | None) -> float | None:
    if not entries:
        return None
    side_u = (side or "").upper()
    if side_u == "LONG":
        return min(entries)
    if side_u == "SHORT":
        return max(entries)
    return entries[0]

def parse_signal_2xclub(message_text: str):
    text = (message_text or "").strip()
    if not text:
        return None

    if is_update_message(text):
        return {"is_update": True}

    t = fa_to_en(text)

    if ("رمزارز" not in t) and (not re.search(r"#([A-Z0-9]+)(?:/USDT)?", t, flags=re.I)):
        return None

    sym = None
    m = re.search(r"رمزارز\s+([A-Za-zآ-ی]+)", t)
    if m:
        sym = m.group(1).upper().strip()
    else:
        m2 = re.search(r"#([A-Z0-9]+)(?:/USDT)?", t)
        if m2:
            sym = m2.group(1).upper().strip()

    symbol = ensure_usdt(sym) if sym else None

    side = None
    if re.search(r"لانگ", t):
        side = "LONG"
    elif re.search(r"شورت", t):
        side = "SHORT"
    elif re.search(r"اسپات\s+خرید", t):
        side = "LONG"

    lev = None
    lm = re.search(r"لوریج\s+(\d+)", t)
    if lm:
        lev = int(lm.group(1))

    entries = []
    em = re.findall(r"(?:در\s+نقطه(?:\s+میانگین)?|در\s+نقاط)\s+([^\n]+)", t)
    if em:
        entries = extract_numbers(em[0])
    else:
        nm = re.findall(r"(?<=نقطه\s)(\d+(?:\.\d+)?)", t)
        if nm:
            entries = [float(x) for x in nm]

    entry = pick_best_entry(entries, side)

    targets = []
    tm = re.search(r"تارگت[:\s]+([^\n]+)", t)
    if tm:
        targets = extract_numbers(tm.group(1))

    stop = None
    sm = re.search(r"استاپ[:\s]+([^\s\n]+)", t)
    if sm:
        nums = extract_numbers(sm.group(1))
        stop = nums[0] if nums else None

    rr = None
    if entry and stop and targets:
        rr = format_rr(entry, stop, targets[0], side)

    return {
        "is_update": False,
        "symbol": symbol,
        "side": side,
        "entry": entry,
        "targets": targets,
        "stop": stop,
        "leverage": lev,
        "rr": rr,
        "market_type": "Crypto",
    }
