import re

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

def fa_to_en(text: str) -> str:
    if not isinstance(text, str):
        return text
    return text.translate(PERSIAN_DIGITS)

def normalize_symbol(sym: str) -> str:
    s = (sym or "").upper().strip()
    s = re.sub(r"\s+", "", s)
    s = s.replace("#", "")
    return s

def ensure_usdt(symbol: str) -> str:
    s = normalize_symbol(symbol)
    if "/USDT" in s:
        s = s.replace("/USDT", "USDT")
    if s.endswith("USDT"):
        return s
    if re.match(r"^[A-Z0-9]{2,15}$", s) and "USD" not in s:
        return f"{s}USDT"
    return s

def is_crypto(symbol: str, text: str) -> bool:
    t = fa_to_en(text or "").upper()
    s = normalize_symbol(symbol or "")
    if any(k in t for k in ["USDT", "BTC", "ETH", "رمزارز"]) or any(k in s for k in ["USDT","BTC","ETH"]):
        return True
    return False

def is_gold(symbol: str, text: str) -> bool:
    s = normalize_symbol(symbol or "")
    t = fa_to_en(text or "").upper()
    return "XAU" in s or "XAUUSD" in s or "طلا" in t
