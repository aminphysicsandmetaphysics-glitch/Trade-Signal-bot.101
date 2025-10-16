import re
from statistics import mean
from ..utils.normalize import (
    ensure_usdt,
    fa_to_en,
    normalize_symbol,
    is_crypto,
)
from ..utils.rr import format_rr
from ..utils.numbers import extract_numbers, normalize_numeric_text
from ..utils.validation import has_valid_name, validate_price_structure
from .parse_signal_2xclub import pick_best_entry


UPDATE_HINTS = [
    r"TP\d*\s*(?:hit|reached|touch|touch(ed)?|done)",
    r"hit\s+TP",
    r"close\s+(?:half|all|manually)",
    r"move\s+SL",
    r"breakeven|break\s*-?even|BE",
    r"remove\s+the\s+order",
    r"cancel\s+the\s+order",
    r"activated",
    r"risk\s+free",
    r"set\s+SL\s+to\s+entry",
    r"SL\s+reached",
]


NON_SYMBOL_TOKENS = {
    "BUY",
    "SELL",
    "LONG",
    "SHORT",
    "MARKET",
    "LIMIT",
    "STOP",
    "ENTRY",
    "PRICE",
    "TP",
    "SL",
    "R",
    "RR",
    "VIP",
    "SIGNAL",
    "POSITION",
    "PIPS",
    "TARGET",
    "RISK",
    "REWARD",
    "ENTRYPRICE",
    "TAKE",
    "PROFIT",
}


KNOWN_SYMBOL_ALIASES = {
    "GOLD": "XAUUSD",
    "XAU": "XAUUSD",
    "USOIL": "USOIL",
    "OIL": "USOIL",
    "WTI": "USOIL",
    "NAS100": "NAS100",
    "NASDAQ": "NAS100",
    "GER40": "GER40",
    "DAX": "GER40",
    "SPX500": "SPX500",
    "US30": "US30",
}


def clean_text(text: str) -> str:
    return normalize_numeric_text(fa_to_en(text or "")).strip()


def is_update_message(text: str) -> bool:
    t = clean_text(text)
    for pat in UPDATE_HINTS:
        if re.search(pat, t, flags=re.I):
            return True
    return False


def detect_symbol(text: str) -> str | None:
    t = clean_text(text)

    # Check for explicit hashtags first.
    m = re.search(r"#\s*([A-Z0-9]{2,}(?:/[A-Z0-9]{2,})?)", t)
    if m:
        symbol = normalize_symbol(m.group(1))
        if "USDT" in symbol:
            symbol = ensure_usdt(symbol)
        return symbol

    # Look for well-known commodity names.
    for alias, sym in KNOWN_SYMBOL_ALIASES.items():
        if re.search(rf"\b{alias}\b", t, flags=re.I):
            return normalize_symbol(sym)

    # Consider uppercase tokens that resemble symbols (e.g. EURUSD, CHFJPY).
    candidates = []
    for token in re.findall(r"\b[A-Z]{3,10}(?:/[A-Z0-9]{3,10})?\b", t):
        token_norm = normalize_symbol(token)
        if token_norm and token_norm not in NON_SYMBOL_TOKENS:
            candidates.append(token_norm)

    if candidates:
        return candidates[0]

    return None


def detect_side(text: str) -> str | None:
    t = clean_text(text)
    if re.search(r"\b(BUY|LONG)\b", t, flags=re.I):
        return "LONG"
    if re.search(r"\b(SELL|SHORT)\b", t, flags=re.I):
        return "SHORT"
    if re.search(r"\bUNLOAD\b", t, flags=re.I):
        return "SHORT"
    if re.search(r"\bLOAD\b", t, flags=re.I):
        return "LONG"
    if re.search(r"\bGRAB\b", t, flags=re.I):
        return "LONG"
    if re.search(r"\bJUMP\s+IN\b", t, flags=re.I):
        return "LONG"
    if re.search(r"\bDEPLOY\b", t, flags=re.I) and "SELL" in t.upper():
        return "SHORT"
    return None


def extract_section_numbers(text: str, patterns: list[str]) -> list[float]:
    t = clean_text(text)
    for pat in patterns:
        m = re.search(pat, t, flags=re.I)
        if m:
            nums = extract_numbers(m.group(1))
            if nums:
                return nums
    return []


def parse_targets(text: str) -> list[float]:
    patterns = [
        r"TP\d*\s*(?:[:\-]|=|\s)\s*([^\n]+)",
        r"Take\s+Profit\s*(?:\d+)?\s*(?:[:\-]|=|\s)\s*([^\n]+)",
        r"Targets?\s*(?:[:\-]|=|\s)\s*([^\n]+)",
    ]

    targets = []
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.I):
            chunk = re.sub(r"\([^)]*\)", " ", m.group(1))
            targets.extend(extract_numbers(chunk))

    # Remove duplicates while preserving order.
    seen = set()
    unique_targets = []
    for val in targets:
        if val not in seen:
            unique_targets.append(val)
            seen.add(val)
    return unique_targets


def parse_signal_generic(message_text: str):
    text = message_text or ""
    if not text.strip():
        return None

    if is_update_message(text):
        return {"is_update": True}

    symbol = detect_symbol(text)

    entry_patterns = [
        r"@\s*([^\n]+)",
        r"Entry\s*(?:Price|Zone)?\s*[:\-]\s*([^\n]+)",
        r"E\s*[:=]\s*([^\n]+)",
        r"(?:Buy|Sell)\s+[A-Z0-9/#]+\s*(?:[:@]|\s)\s*([0-9\-\.,\s]+?)(?=\s*(?:\(|SL|TP|Stop|Take|Target|RR|Risk|$))",
        r"[A-Z0-9/#]+\s+(?:Buy|Sell)\s*(?:[:@]|\s)\s*([0-9\-\.,\s]+?)(?=\s*(?:\(|SL|TP|Stop|Take|Target|RR|Risk|$))",
    ]
    entries = extract_section_numbers(text, entry_patterns)

    if not entries:
        # Try to detect numbers after the instrument name (e.g. "Gold 4039-4034").
        if symbol:
            sym_pattern = symbol.replace("USDT", "")
            m = re.search(rf"{sym_pattern}\s*([\d\-\.\s]+)", clean_text(text), flags=re.I)
            if m:
                entries = extract_numbers(m.group(1))

    if not entries:
        return None

    side = detect_side(text)

    targets = parse_targets(text)

    stop_patterns = [
        r"SL\s*(?:[:\-]|=|\s)\s*([^\n]+)",
        r"Stop\s*Loss\s*(?:[:\-]|=|\s)\s*([^\n]+)",
        r"Stop\s*(?:[:\-]|=|\s)\s*([^\n]+)",
    ]
    stop_candidates = extract_section_numbers(text, stop_patterns)
    stop = stop_candidates[0] if stop_candidates else None

    entry = pick_best_entry(entries, side)

    if not side and targets and entry:
        first_target = targets[0]
        if stop:
            if first_target > entry >= stop or (stop and stop < entry < first_target):
                side = "LONG"
            elif first_target < entry <= stop or (stop and stop > entry > first_target):
                side = "SHORT"
        else:
            side = "LONG" if first_target > entry else "SHORT"

    # Fallback if entry is a range and side is still unknown: compare average target to entry mean.
    if not side and targets:
        avg_entry = mean(entries)
        avg_target = mean(targets)
        side = "LONG" if avg_target >= avg_entry else "SHORT"

    if not symbol:
        # Attempt to infer symbol from context after determining side.
        if re.search(r"GOLD", clean_text(text), flags=re.I):
            symbol = "XAUUSD"

    if not symbol:
        return None

    if not has_valid_name(symbol):
        return None

    if entry is None or stop is None or not targets:
        # At minimum we expect entry, stop, and at least one target for a valid signal.
        return None

    if not validate_price_structure(entry, targets, stop, side):
        return None

    market_type = "Crypto" if is_crypto(symbol, text) else "Forex"
    if symbol and market_type == "Crypto":
        symbol = ensure_usdt(symbol)

    rr = None
    if entry is not None and stop is not None and targets:
        rr = format_rr(entry, stop, targets[0], side)

    parsed = {
        "is_update": False,
        "symbol": symbol,
        "side": side,
        "entry": entry,
        "targets": targets,
        "stop": stop,
        "rr": rr,
        "market_type": market_type,
    }

    return parsed
