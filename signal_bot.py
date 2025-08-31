"""Telethon wrapper for forwarding and parsing trading signals.

This module encapsulates all Telegram interaction.  It normalises
channel identifiers, listens to new messages from a list of source
channels and forwards or copies them to a single destination channel.

When forwarding fails due to content protection, the bot will fall
back to copying the text and any attached media.
"""

from __future__ import annotations

import sys, logging, os


def setup_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    if not root.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        root.addHandler(h)
    root.setLevel(level)


setup_logging()
log = logging.getLogger("signal_bot")

import asyncio
import re
import hashlib
import time
from datetime import datetime, timezone, timedelta
from collections import deque
from threading import Lock
from typing import List, Dict, Optional, Iterable, Callable, Union, Deque, Tuple, Any

from jinja2 import Environment, FileSystemLoader, Template, select_autoescape
from markupsafe import escape

from telethon import TelegramClient, events
from telethon.errors import (
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
)
from telethon.sessions import StringSession

# ----------------------------------------------------------------------------
# Signal parsing (REPLACED / IMPROVED)
# ----------------------------------------------------------------------------

# نمادها/سیمبل‌ها
# Match optional hashtag followed by either a single token alias or a
# pair of tokens separated by a slash. Delimiters are stripped during
# normalisation.
PAIR_RE = re.compile(r"(?:#)?([A-Z]{3}/[A-Z]{3,6}|[A-Z]{3,6})\b")

# Supported currency codes for validating symbol guesses
CURRENCY_CODES = {
    "USD",
    "EUR",
    "GBP",
    "AUD",
    "CAD",
    "NZD",
    "CHF",
    "JPY",
    "BTC",
    "ETH",
    "LTC",
    "XAU",
    "XAG",
    "SGD",
    "HKD",
    "NOK",
    "SEK",
    "ZAR",
    "TRY",
    "RUB",
    "CNY",
    "CNH",
    "MXN",
    "BRL",
    "INR",
    "SAR",
    "AED",
    "PLN",
}

# Map common aliases and instrument names to canonical symbols
ALIAS_MAP = {
    # Commodities
    "GOLD": "XAUUSD",
    "XAU": "XAUUSD",
    "SILVER": "XAGUSD",
    "WTI": "USOIL",
    "USOIL": "USOIL",
    "UKOIL": "UKOIL",
    "BRENT": "UKOIL",
    # Indices
    "NAS": "NAS100",
    "NAS100": "NAS100",
    "US30": "US30",
    "DJI": "US30",
    "DAX": "GER40",
    "GER40": "GER40",
    # Major crypto tickers (USDT pairs)
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "BNB": "BNBUSDT",
    "SOL": "SOLUSDT",
    "XRP": "XRPUSDT",
    "ADA": "ADAUSDT",
    "DOGE": "DOGEUSDT",
    "DOT": "DOTUSDT",
    "LTC": "LTCUSDT",
    "LINK": "LINKUSDT",
    "BCH": "BCHUSDT",
    "TRX": "TRXUSDT",
    "XLM": "XLMUSDT",
    "ETC": "ETCUSDT",
    "XMR": "XMRUSDT",
    "NEO": "NEOUSDT",
    "EOS": "EOSUSDT",
    "IOTA": "IOTAUSDT",
    "XTZ": "XTZUSDT",
    "UNI": "UNIUSDT",
    "AVAX": "AVAXUSDT",
    "MATIC": "MATICUSDT",
}

# Normalise symbol strings to canonical form
def normalize_symbol(raw: str) -> str:
    s = (raw or "").upper().lstrip("#").strip()
    s = re.sub(r"[\s/]+", "", s)
    return ALIAS_MAP.get(s, s)

# Known non-FX instruments matched directly
KNOWN_INSTRUMENTS = {"XAUUSD", "XAGUSD", "USOIL", "UKOIL", "NAS100", "US30", "GER40", "BTCUSDT"}
# عدد
NUM_RE = re.compile(r"(-?\d+(?:\.\d+)?)")
# R/R
RR_RE = re.compile(
    r"(\b(?:R\s*/\s*R|Risk[- ]?Reward|Risk\s*:\s*Reward)\b[^0-9]*?(\d+(?:\.\d+)?)\s*[:/]\s*(\d+(?:\.\d+)?))",
    re.IGNORECASE,
)

# حالت‌های پوزیشن
POS_VARIANTS = [
    ("BUY LIMIT", "Buy Limit"),
    ("SELL LIMIT", "Sell Limit"),
    ("BUY STOP", "Buy Stop"),
    ("SELL STOP", "Sell Stop"),
    ("BUY", "Buy"),
    ("SELL", "Sell"),
]

# کلیدواژه‌های نویز/آپدیت/تبلیغ که باید نادیده بگیریم
# این فهرست به‌صورت دوزبانه (انگلیسی/فارسی) نگهداری می‌شود و همگی به حروف
# کوچک و بدون نیم‌فاصله نرمال می‌شوند.
NON_SIGNAL_HINTS = [
    # English noise/update hints
    "activated",
    "tp reached",
    "result so far",
    "screenshots",
    "cheers",
    "high-risk setup",
    "move sl",
    "put your sl",
    "risk free",
    "close",
    "closed",
    "partial close",
    "delete",
    "running",
    "trade - update",
    "update",
    "analysis",
    "setup",
    "guide",
    "watchlist",
    "broker",
    "subscription",
    "contact",
    "admin",
    "tp almost",
    "tp hit",
    "sl reached",
    "sl hit",
    "profits",
    "week",
    "friday",
    "make tp",
    "make sl",
    "make tp/sl",
    "change tp",
    "change sl",
    "change tp/sl",
    "make sure",
    "all signals",
    "add position",
    "upgrade your subscription",
    # Persian noise/update hints
    "آپدیت",
    "فعال شد",
    "اسکرین شات",
    "اسکرینشات",
    "تبریک",
]

# الگوی حذف ایموجی‌ها قبل از بررسی کلیدواژه‌ها
EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"  # flags
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F700-\U0001F77F"  # alchemical symbols
    "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
    "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
    "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
    "\U0001FA00-\U0001FA6F"  # Chess Symbols etc.
    "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
    "\u2600-\u26FF"          # Misc symbols
    "\u2700-\u27BF"          # Dingbats
    "]+",
    flags=re.UNICODE,
)

# Lines that are purely visual dividers ("----", "====", etc.)
DIVIDER_LINE_RE = re.compile(r"^[\s\-\–\—\_\=\·\.\•\*➖]+$")

TP_KEYS = ["tp", "take profit", "take-profit", "t/p", "t p"]
ENTRY_KEYS = ["entry price", "entry", "e:"]

# الگوی استخراج عدد پس از SL یا Stop Loss
SL_VALUE_RE = re.compile(
    r"\b(?:SL|Stop[-\s]*Loss)\s*[:\-]?\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

# Explicit TP/Target line detector and numeric extractor excluding unit-suffixed numbers
TP_LINE_RE = re.compile(r"\b(?:tp\d*|target)\b", re.IGNORECASE)
TP_VALUE_RE = re.compile(
    r"(-?\d+(?:\.\d+)?)(?!\s*(?:pips?|pip|points?|pts?|percent|%))\b",
    re.IGNORECASE,
)

# Direction synonyms used across parsers
BUY_TERMS = ["buy", "buying", "long", "purchase", "grab"]
SELL_TERMS = ["sell", "selling", "short", "offload", "unload", "dump", "ditch"]

BUY_SYNONYMS = re.compile(rf"\b({'|'.join(BUY_TERMS)})\b", re.IGNORECASE)
SELL_SYNONYMS = re.compile(rf"\b({'|'.join(SELL_TERMS)})\b", re.IGNORECASE)

# Special-case parsing for the "United Kings" channels
# (IDs taken from known public channels)
UNITED_KINGS_CHAT_IDS = {
    -1002223574325,
    -1002709043208,
}

# United Kings specific regex patterns
# Entry is provided as a range separated by a dash ("@" optional, various unicode dashes)
UK_RANGE_RE = re.compile(
    r"@?\s*(-?\d+(?:\.\d+)?)\s*[-\u2010-\u2015]\s*(-?\d+(?:\.\d+)?)"
)
UK_SL_RE = re.compile(r"\bS\s*L\s*[:@-]?\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
UK_TP_RE = re.compile(r"\bT\s*P\s*\d*\s*[:@-]?\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
UK_NOISE_LINES = [
    re.compile(r"united\s+kings", re.IGNORECASE),
    re.compile(r"tp\s+(?:hit|reached)", re.IGNORECASE),
    re.compile(r"tp\s*almost", re.IGNORECASE),
    re.compile(r"sl\s+(?:hit|reached)", re.IGNORECASE),
    re.compile(r"break\s*even", re.IGNORECASE),
    re.compile(r"risk\s*free", re.IGNORECASE),
    re.compile(r"result", re.IGNORECASE),
]

UK_GOLD_RE = re.compile(r"\bgold\b", re.IGNORECASE)
UK_PRICE_RE = re.compile(r"@\s*-?\d+(?:\.\d+)?")
UK_ACTION_RE = re.compile(
    rf"\b({'|'.join(BUY_TERMS + SELL_TERMS)})\b",
    re.IGNORECASE,
)

# Entry range detector used to spot patterns like '@1234-1250'
# Entry ranges may use various dash-like characters between the numbers.
# Accept common forms such as hyphen-minus (-), en dash (–), em dash (—)
# and the unicode minus sign (−).
ENTRY_RANGE_RE = re.compile(
    r"@\s*\d+(?:\.\d+)?\s*[-–—−]\s*\d+(?:\.\d+)?"
)

# Mapping of chat IDs to profile options controlling parsing behaviour.
# Example: {1234: {"allow_entry_range": True, "show_entry_range_only": True}}
CHANNEL_PROFILES: Dict[int, Dict[str, Any]] = {}


def resolve_profile(chat_id: int) -> Dict[str, Any]:
    """Return the profile dict associated with a chat ID."""
    return CHANNEL_PROFILES.get(int(chat_id), {})


def normalize_numbers(text: str) -> str:
    """Translate Persian/Arabic digits and separators to ASCII equivalents."""
    if not text:
        return ""

    # Map Eastern Arabic and Persian digits to Western Arabic numerals
    digit_map = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
    digit_map.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})

    # Separate mappings for thousands and decimal separators
    thousands_map = {ord("٬"): None, ord(","): None}
    decimal_map = {ord("٫"): "."}

    # Apply mappings: strip thousands separators before decimals
    text = text.translate(digit_map)
    text = text.translate(thousands_map)
    text = text.translate(decimal_map)

    return text


def guess_symbol(text: str) -> Optional[str]:
    m = PAIR_RE.search((text or "").upper())
    if not m:
        return None
    sym = normalize_symbol(m.group(1))
    if sym in KNOWN_INSTRUMENTS or sym in ALIAS_MAP.values():
        return sym
    if len(sym) == 6:
        base, quote = sym[:3], sym[3:]
        if base in CURRENCY_CODES and quote in CURRENCY_CODES:
            return sym
    return None


def guess_position(text: str) -> Optional[str]:
    up = (text or "").upper()
    for raw, norm in POS_VARIANTS:
        if raw in up:
            return norm
    if BUY_SYNONYMS.search(text or ""):
        return "Buy"
    if SELL_SYNONYMS.search(text or ""):
        return "Sell"
    return None


def classic_extract_entry(lines: List[str]) -> Optional[str]:
    """Extract entry price using classic heuristics.

    Priority is given to numbers that appear immediately after explicit
    ``Entry``/``Price`` keywords.  As a fallback, numbers near position
    keywords (``Buy``/``Sell``) are considered.  Any numbers following
    ``TP``/``SL`` patterns are ignored to avoid false positives when all
    values appear on a single line.
    """

    # 1) Explicit entry/price keywords
    for l in lines:
        ll = l.lower()
        if any(k in ll for k in ENTRY_KEYS):
            for nm in NUM_RE.finditer(l):
                prefix = ll[: nm.start()]
                if re.search(r"(tp\d*|take\s*profit\d*|sl|stop\s*loss)\s*$", prefix):
                    continue
                return nm.group(1)

    # 2) Fallback to numbers near position keywords
    for l in lines:
        ll = l.lower()
        if not re.search(r"\b(buy|sell)\b", ll):
            continue
        for nm in NUM_RE.finditer(l):
            prefix = ll[: nm.start()]
            if re.search(r"(tp\d*|take\s*profit\d*|sl|stop\s*loss)\s*$", prefix):
                continue
            if re.search(r"(buy|sell)(?:\s+(limit|stop))?\s*$", prefix):
                return nm.group(1)

    return None


# Backwards compatibility for older code/tests
extract_entry = classic_extract_entry


def extract_sl(lines: List[str]) -> Optional[str]:
    """Extract the stop loss value from signal lines.

    Only numbers that immediately follow an ``SL`` or ``Stop Loss`` keyword
    are considered. Lines containing the keyword without a subsequent number
    are ignored to avoid accidentally capturing unrelated numeric values.
    """

    for l in lines:
        m = SL_VALUE_RE.search(l)
        if m:
            return m.group(1)
    return None


def classic_extract_tps(lines: List[str]) -> List[str]:
    """Extract take profit values from lines using simple heuristics.

    Only lines containing an explicit ``TP`` or ``Target`` keyword are
    considered.  All numeric values in those lines are returned unless they
    are immediately followed by unit words such as ``pips``.  Numbers that are
    part of labels like ``TP1`` or ``Target 2`` are ignored.  Duplicate values
    are removed while preserving the original order.
    """

    tps: List[str] = []
    for l in lines:
        if not TP_LINE_RE.search(l):
            continue

        for num in TP_VALUE_RE.findall(l):
            # Skip TP/Target indices like "TP1" or "Target 2"
            if re.fullmatch(r"\d+", num) and re.search(
                r"\b(?:tp|target)(?:\s*[:\-]?\s*)?" + num + r"\b",
                l,
                re.IGNORECASE,
            ):
                continue
            tps.append(num)

    # Deduplicate while preserving order
    seen = set()
    uniq: List[str] = []
    for x in tps:
        if x not in seen:
            uniq.append(x)
            seen.add(x)
    return uniq


def extract_tps(lines: List[str]) -> List[str]:
    tps: List[str] = []
    for l in lines:
        ll = l.lower()
        if not any(k in ll for k in TP_KEYS):
            continue

        # 1) اول تلاش کن الگوی استاندارد «TPn : قیمت» یا «Take Profit n : قیمت» را بگیری
        m = re.search(
            r'\b(?:TP|Take\s+Profit)\s*\d*\s*[:\-]\s*(-?\d+(?:\.\d+)?)',
            l,
            re.IGNORECASE,
        )
        if m:
            tps.append(m.group(1))
            continue

        # 2) در غیر این صورت، اولین عددی را بگیر که تا 6 کاراکتر بعدش "pip/pips" نیامده
        #    (تا «80 pips» به‌عنوان TP شمرده نشود) و عددهای خیلی کوچکِ شاخص (مثل "1" در "TP1") حذف شوند.
        for nm in re.finditer(r'(-?\d+(?:\.\d+)?)(?![^\n]{0,6}\s*pips?\b)', l, re.IGNORECASE):
            num = nm.group(1)

            # اگر خط شامل TP بود، اعداد خیلی کوچک و بدون اعشار (شماره TP) را رد کن
            if (
                re.search(r'\b(?:TP|Take\s+Profit)\b', l, re.IGNORECASE)
                and re.fullmatch(r'\d+', num)
            ):
                # معمولاً شماره‌های TP کوچک‌اند؛ ردش کن
                if int(num) <= 10:
                    continue

            tps.append(num)
            break  # از هر خط فقط یک TP

    # یکتا کردن با حفظ ترتیب
    seen = set()
    uniq: List[str] = []
    for x in tps:
        if x not in seen:
            uniq.append(x)
            seen.add(x)
    return uniq


def extract_rr(text: str) -> Optional[str]:
    m = RR_RE.search(text or "")
    if m:
        return f"{m.group(2)}/{m.group(3)}"
    return None


def calculate_rr(entry: str, sl: str, tp: str) -> Optional[str]:
    """Calculate risk/reward ratio from entry, stop loss and first take profit."""
    try:
        e, s, t = float(entry), float(sl), float(tp)
    except Exception:
        return None
    risk = abs(e - s)
    reward = abs(t - e)
    if risk <= 0 or reward <= 0:
        return None

    def fmt(x: float) -> str:
        return f"{x:.2f}".rstrip("0").rstrip(".")

    if risk >= reward:
        return f"{fmt(risk / reward)}/1"
    else:
        return f"1/{fmt(reward / risk)}"


def _normalize_hint_text(text: str) -> str:
    """Return *text* with half-spaces and emojis normalised for matching."""
    if not text:
        return ""
    text = text.replace("\u200c", " ")
    text = EMOJI_RE.sub(" ", text)
    return text


def looks_like_update(text: str) -> bool:
    t = _normalize_hint_text(text).lower()
    return any(key in t for key in NON_SIGNAL_HINTS)


def looks_like_noise_or_update(text: str) -> bool:
    """Backward compatible wrapper for ``looks_like_update``."""
    return looks_like_update(text)


def _strip_noise_lines(lines: list[str]) -> list[str]:
    """Normalize and remove boilerplate from *lines*.

    Each line is stripped of surrounding whitespace. Blank lines, visual
    divider lines and a few known header phrases are removed. Lines that do not
    mention an entry ``@`` or the tokens ``SL``/``TP`` and also don't look like
    core signal information (symbols, positions or numeric data) are considered
    advisory and dropped. Remaining lines are returned.
    """

    cleaned: List[str] = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        if DIVIDER_LINE_RE.fullmatch(raw):
            continue
        low = raw.lower()
        if low.startswith("trade alert"):
            continue
        if low.startswith("alright united kings"):
            continue
        if low.startswith("tyler here"):
            continue

        if "@" not in raw and "sl" not in low and "tp" not in low:
            if (
                NUM_RE.search(raw)
                or raw.startswith("#")
                or re.search(r"\b(buy|sell|entry|position)\b", low)
                or BUY_SYNONYMS.search(raw)
                or SELL_SYNONYMS.search(raw)
            ):
                cleaned.append(raw)
            continue

        cleaned.append(raw)

    return cleaned


def is_valid(signal: Dict) -> bool:
    entry_or_range = signal.get("entry") or signal.get("extra", {}).get("entries", {}).get("range")
    return all([
        signal.get("symbol"),
        signal.get("position"),
        entry_or_range,
        signal.get("sl"),
    ]) and len(signal.get("tps", [])) >= 1


def validate_directional_consistency(signal: Dict) -> bool:
    """Check that TP and SL are on the correct side of entry.

    For ``BUY`` signals every take-profit target must be strictly above the
    entry price while the stop loss must be below it.  ``SELL`` signals require
    the opposite relationship.  If values cannot be parsed as floats the
    function defaults to ``True`` leaving validation to other layers.
    """

    try:
        entry = float(signal.get("entry"))
        sl = float(signal.get("sl"))
        tps = [float(tp) for tp in signal.get("tps", [])]
    except Exception:
        return True

    pos = (signal.get("position") or "").upper()
    if pos.startswith("BUY"):
        if sl >= entry:
            log.info(
                f"IGNORED (buy but SL {signal['sl']} >= entry {signal['entry']})"
            )
            return False
        if any(tp <= entry for tp in tps):
            log.info(
                f"IGNORED (buy but TP {tps[0]} <= entry {signal['entry']})"
            )
            return False
    elif pos.startswith("SELL"):
        if sl <= entry:
            log.info(
                f"IGNORED (sell but SL {signal['sl']} <= entry {signal['entry']})"
            )
            return False
        if any(tp >= entry for tp in tps):
            log.info(
                f"IGNORED (sell but TP {tps[0]} >= entry {signal['entry']})"
            )
            return False
    return True


def _has_entry_range(text: str) -> bool:
    """Return True if ``text`` contains an entry range like ``@1234-1250``."""
    return bool(ENTRY_RANGE_RE.search(text))


def to_unified(signal: Dict, chat_id: int, extra: Optional[Dict] = None) -> str:
    extra = extra if extra is not None else signal.get("extra", {})
    profile = resolve_profile(chat_id)
    show_range_only = extra.get("show_entry_range_only")
    if show_range_only is None:
        show_range_only = profile.get("show_entry_range_only")

    parts: List[str] = []
    parts.append(f"📊 #{signal['symbol']}")
    parts.append(f"📉 Position: {signal['position']}")
    rr = signal.get("rr")
    if rr:
        parts.append(f"❗️ R/R : {rr}")

    entry_range = extra.get("entries", {}).get("range")
    if entry_range:
        if not show_range_only:
            parts.append(f"💲 Entry Price : {signal['entry']}")
        try:
            lo, hi = entry_range
            parts.append(f"🎯 Entry Range : {lo} – {hi}")
        except Exception:
            pass
    else:
        parts.append(f"💲 Entry Price : {signal['entry']}")

    for i, tp in enumerate(signal["tps"], 1):
        parts.append(f"✔️ TP{i} : {tp}")
    parts.append(f"🚫 Stop Loss : {signal['sl']}")
    return "\n".join(parts)


_jinja_env = Environment(
    loader=FileSystemLoader(os.getenv("TEMPLATE_DIR", "templates")),
    autoescape=select_autoescape(["html", "xml"], default_for_string=True),
)


def render_template(template: str, context: Dict[str, Any]) -> str:
    """Render a Jinja2 *template* using *context*.

    The *template* parameter may be the name of a template file located in the
    directory specified by ``TEMPLATE_DIR`` (default ``templates``) or a raw
    template string.  ``context`` provides the variables available to the
    template.
    """

    if template.endswith(('.j2', '.jinja2', '.html')) and os.path.exists(
        os.path.join(os.getenv("TEMPLATE_DIR", "templates"), template)
    ):
        tmpl = _jinja_env.get_template(template)
    else:
        template = escape(template)
        tmpl = _jinja_env.from_string(str(template))
    return tmpl.render(**context)


def _clean_uk_lines(text: str) -> List[str]:
    """Normalise United Kings message lines removing known noise."""
    lines: List[str] = []
    for raw in (text or "").splitlines():
        raw = raw.strip()
        raw = re.sub(r"^[\-•\s]+", "", raw)
        if not raw:
            continue
        # Skip noise or promotional lines
        if any(pat.search(raw) for pat in UK_NOISE_LINES):
            continue
        lines.append(raw)
    return lines


def _looks_like_united_kings(text: str) -> bool:
    """Heuristic check for United Kings style messages.

    A message is considered United Kings style when it mentions gold,
    includes either an ``@price`` or a ``lo–hi`` range and contains an
    action verb such as Buy, Sell, Grab, Purchase or Unload.  Phrases like
    ``we're buying`` or ``we're selling`` are also recognised.
    """

    if not text:
        return False
    if not UK_GOLD_RE.search(text):
        return False
    if not (UK_PRICE_RE.search(text) or UK_RANGE_RE.search(text)):
        return False
    if not UK_ACTION_RE.search(text):
        return False
    return True


def _validate_tp_sl(
    position: str,
    entry: str,
    sl: str,
    tps: List[str],
    entry_range: Optional[Tuple[str, str]] = None,
) -> bool:
    """Return True if TP/SL values are consistent with *entry*.

    For ``BUY`` positions the stop loss must be below the entry price and at
    least one take-profit target must be above it.  ``SELL`` signals require the
    opposite.  When an ``entry_range`` is supplied, the lower bound is used for
    stop-loss validation and the upper bound for take-profit checks.  A warning
    is emitted if any TP or SL falls *within* the provided range, as this often
    indicates an inconsistent signal.
    """

    try:
        e = float(entry)
        sl_v = float(sl)
        tp_vals = [float(tp) for tp in tps]
        lo, hi = e, e
        if entry_range:
            lo, hi = sorted(float(x) for x in entry_range)

        pos = position.upper()
        if pos.startswith("BUY"):
            if sl_v >= lo:
                log.info(f"IGNORED (buy but SL {sl} >= entry {entry})")
                return False
            if any(tv < lo for tv in tp_vals):
                log.info(f"IGNORED (buy but TP {tp_vals[0]} < entry {entry})")
                return False
            if all(tv < (hi if entry_range else e) for tv in tp_vals):
                log.info(f"IGNORED (buy but all TP < entry {entry})")
                return False
            if entry_range and (
                any(lo <= tv <= hi for tv in tp_vals) or lo < sl_v < hi
            ):
                log.warning("TP/SL inside entry range")
                return False
        elif pos.startswith("SELL"):
            boundary = lo if entry_range else e
            if sl_v <= boundary:
                log.info(f"IGNORED (sell but SL {sl} <= entry {entry})")
                return False
            if any(tv > boundary for tv in tp_vals):
                log.info(f"IGNORED (sell but TP {tp_vals[0]} > entry {entry})")
                return False
            if all(tv > boundary for tv in tp_vals):
                log.info(f"IGNORED (sell but all TP > entry {entry})")
                return False
            if entry_range and (
                any(lo <= tv <= hi for tv in tp_vals) or lo < sl_v < hi
            ):
                log.warning("TP/SL inside entry range")
                return False
    except Exception:
        pass
    return True


def parse_signal_united_kings(text: str, chat_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Parse a United Kings style signal.

    Parameters
    ----------
    text : str
        Raw message body from the source channel.
    chat_id : int
        Numeric identifier of the channel the message originated from.

    Notes
    -----
    The parser honours the global ``skip_rr_for`` collection, skipping
    risk/reward ratio calculation when ``chat_id`` is present in that set.
    For recognised entry ranges, the lower bound is used if an ``@`` symbol
    precedes the range (``@1900-1910``).  When the ``@`` is absent, the
    midpoint of the provided range becomes the effective entry price.

    Returns
    -------
    Tuple[Optional[str], Optional[str]]
        A pair of ``(result, reason)`` where ``result`` is the formatted
        signal string or ``None`` if the message is ignored and ``reason``
        contains the ignore cause.
    """
    if looks_like_update(text):
        return None, "update/noise"

    lines = _clean_uk_lines(text)
    if not lines:
        return None, "empty"
    symbol = normalize_symbol("XAUUSD")
    if not symbol:
        log.info("IGNORED (no symbol)")
        return None

    # Entry range like '@1900-1910' or '1900-1910'
    m = UK_RANGE_RE.search(text)
    if not m:
        return None, "no entry range"

    # Determine direction by inspecting a 120 character window around the match
    start = max(0, m.start() - 120)
    end = min(len(text), m.end() + 120)
    window = text[start:end]
    position = ""
    if BUY_SYNONYMS.search(window):
        position = "Buy"
    elif SELL_SYNONYMS.search(window):
        position = "Sell"
    else:
        position = guess_position(text) or ""
    if not position:
        return None, "no position"
    p1, p2 = float(m.group(1)), float(m.group(2))
    lo, hi = (p1, p2) if p1 <= p2 else (p2, p1)

    def _fmt(x: float) -> str:
        s = f"{x:.5f}".rstrip("0").rstrip(".")
        return s

    range_str = m.group(0)
    if "@" in range_str:
        calc_entry = f"{lo}"
    else:
        mid = (lo + hi) / 2
        calc_entry = _fmt(mid)
    entry_range = [_fmt(lo), _fmt(hi)]

    # SL
    sl = ""
    for l in lines:
        sm = UK_SL_RE.search(l)
        if sm:
            sl = sm.group(1)
            break
    if not sl:
        return None, "no SL"

    # TPs
    tps: List[str] = []
    for l in lines:
        for tm in UK_TP_RE.finditer(l):
            tps.append(tm.group(1))
    # unique preserve order
    seen = set()
    tps = [x for x in tps if not (x in seen or seen.add(x))]
    if not tps:
        return None, "no TP"

    rr = extract_rr(text)
    if not rr:
        rr = calculate_rr(calc_entry, sl, tps[0])

    extra = {
        "entries": {"range": entry_range},
        "show_entry_range_only": True,
    }
    signal = {
        "symbol": symbol,
        "position": position,
        "entry": None,
        "sl": sl,
        "tps": tps,
        "rr": rr,
        "extra": extra,
    }

    if not is_valid(signal):
        return None, "invalid"
    if not validate_directional_consistency(signal):
        return None, "invalid"
    if not _validate_tp_sl(position, calc_entry, sl, tps, tuple(entry_range)):
        return None, "invalid"

    return to_unified(signal, chat_id, extra), None


def parse_channel_four(text: str, chat_id: int) -> Optional[str]:
    """Parser for Channel Four style messages supporting entry ranges."""
    if looks_like_update(text):
        log.info("IGNORED (update/noise)")
        return None
    lines = _strip_noise_lines((text or "").splitlines())
    text = "\n".join(lines)
    if not lines:
        log.info("IGNORED (empty)")
        return None

    symbol = normalize_symbol(guess_symbol(text) or "")
    if not symbol:
        log.info("IGNORED (no symbol)")
        return None
    position = guess_position(text) or ""
    entry = extract_entry(lines) or ""
    sl = extract_sl(lines) or ""
    tps = extract_tps(lines)
    rr = extract_rr(text)
    if not rr and entry and sl and tps:
        rr = calculate_rr(entry, sl, tps[0])

    entry_range: Optional[Tuple[str, str]] = None
    for l in lines:
        ll = l.lower()
        if any(k in ll for k in ENTRY_KEYS):
            m = re.search(r"(-?\d+(?:\.\d+)?)[^\d]+(-?\d+(?:\.\d+)?)", l)
            if m:
                entry_range = (m.group(1), m.group(2))
                if not entry:
                    entry = m.group(1)
                break

    signal = {
        "symbol": symbol,
        "position": position,
        "entry": entry,
        "sl": sl,
        "tps": tps,
        "rr": rr,
        "extra": {},
    }
    if entry_range:
        signal["extra"]["entries"] = {"range": entry_range}

    if not is_valid(signal):
        log.info(f"IGNORED (invalid) -> {signal}")
        return None
    if not validate_directional_consistency(signal):
        return None
    if not _validate_tp_sl(position, entry, sl, tps, entry_range):
        return None

    return to_unified(signal, chat_id, signal.get("extra", {}))


def parse_signal_classic(
    text: str,
    chat_id: int,
    profile: Dict[str, Any] | None = None,
    *,
    return_meta: bool = False,
) -> Optional[Union[str, Tuple[str, Dict[str, Any]]]]:
    profile = profile or {}
    text = normalize_numbers(text)
    if not text:
        log.info("IGNORED (empty)")
        return None

    lines = _strip_noise_lines(text.splitlines())
    text = "\n".join(lines)
    if not text:
        log.info("IGNORED (empty)")
        return None

    if looks_like_update(text):
        log.info("IGNORED (update/noise)")
        return None

    if _has_entry_range(text):
        if profile.get("allow_entry_range"):
            try:
                return parse_channel_four(text, chat_id)
            except Exception as e:
                log.debug(f"Entry range parser failed: {e}")
                return None
        else:
            log.info("IGNORED (entry range not allowed)")
            return None

    symbol = normalize_symbol(guess_symbol(text) or "")
    if not symbol:
        log.info("IGNORED (no symbol)")
        return None
    position = guess_position(text) or ""
    entry = extract_entry(lines) or ""
    sl = extract_sl(lines) or ""
    tps = extract_tps(lines)
    rr = extract_rr(text)
    if not rr and entry and sl and tps:
        rr = calculate_rr(entry, sl, tps[0])

    signal = {
        "symbol": symbol,
        "position": position,
        "entry": entry,
        "sl": sl,
        "tps": tps,
        "rr": rr,
    }

    if not is_valid(signal):
        log.info(f"IGNORED (invalid) -> {signal}")
        return None

    if not validate_directional_consistency(signal):
        return None

    result = to_unified(signal, chat_id, signal.get("extra", {}))
    if return_meta:
        return result, signal
    return result

def parse_signal(
    text: str,
    chat_id: int,
    profile: Dict[str, Any] | None = None,
    *,
    return_meta: bool = False,
) -> Optional[Union[str, Tuple[str, Dict[str, Any]]]]:
    profile = profile or {}
    text = normalize_numbers(text)
    if not text:
        log.info("IGNORED (empty)")
        return None

    lines = _strip_noise_lines(text.splitlines())
    text = "\n".join(lines)
    if not text:
        log.info("IGNORED (empty)")
        return None

    is_united_kings = chat_id in UNITED_KINGS_CHAT_IDS or _looks_like_united_kings(text)
    if is_united_kings:
        try:
            res, reason = parse_signal_united_kings(text, chat_id)
            if res is not None:
                return res
            if reason in {"no entry range", "no position"}:
                return parse_signal_classic(text, chat_id, profile=profile, return_meta=return_meta)
            else:
                if reason:
                    log.info(f"IGNORED ({reason})")
                return None
        except Exception as e:
            log.debug(f"United Kings parser failed: {e}")
            return parse_signal_classic(text, chat_id, profile=profile, return_meta=return_meta)

    return parse_signal_classic(text, chat_id, profile=profile, return_meta=return_meta)

# ----------------------------------------------------------------------------
# Dedupe helper — اثرانگشت محتوا
# ----------------------------------------------------------------------------
def _content_fingerprint(ev_msg, chat_id: int) -> str:
    """
    اثرانگشت محتوا: متن نرمال‌شده + شناسه‌ی مدیا (photo/document) + شناسه کانال.
    برای جلوگیری از ارسال تکراری پیام‌های مشابه در یک بازه زمانی.
    """
    parts = []
    text = (getattr(ev_msg, "message", None) or "").strip()
    text = re.sub(r"\s+", " ", text).lower()
    parts.append(text)

    media = getattr(ev_msg, "media", None)
    media_id = ""
    if media:
        try:
            if getattr(ev_msg, "photo", None) and getattr(ev_msg.photo, "id", None):
                media_id = f"photo:{ev_msg.photo.id}"
            elif getattr(ev_msg, "document", None) and getattr(ev_msg.document, "id", None):
                media_id = f"doc:{ev_msg.document.id}"
        except Exception:
            pass
    parts.append(media_id)
    parts.append(str(chat_id))

    return hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()



# ----------------------------------------------------------------------------
# Channel identifier normalisation (kept from your version)
# ----------------------------------------------------------------------------

def _norm_chat_identifier(x: Union[int, str]) -> Union[int, str]:
    """Normalise channel identifiers: '@name' / 'https://t.me/name' / numeric."""
    if isinstance(x, int):
        # Ensure numeric identifiers are coerced to Telegram channel IDs
        return _coerce_channel_id(x)

    s = (x or "").strip()
    s = re.sub(r"^https?://t\.me/", "", s, flags=re.IGNORECASE)
    s = s.lstrip("@").strip()

    # If the remaining string is purely numeric, convert to int and coerce
    if re.fullmatch(r"-?\d+", s):
        return _coerce_channel_id(int(s))

    return s


def _coerce_channel_id(x: Union[int, str]) -> Union[int, str]:
    """Coerce positive numeric IDs to Telegram channel form -100XXXXXXXXXX."""
    if isinstance(x, int):
        return x if x < 0 else int("-100" + str(x))

    if isinstance(x, str) and re.fullmatch(r"\d+", x):
        return int("-100" + x)

    return x


# ----------------------------------------------------------------------------
# Statistics helper
# ----------------------------------------------------------------------------


class BotStats:
    """Thread-safe counters and recent message storage."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.received = 0
        self.filtered = 0
        self.parsed = 0
        self.sent = 0
        self.rejected = 0
        self.messages: Deque[dict] = deque(maxlen=20)

    def increment(self, field: str, amount: int = 1) -> None:
        with self._lock:
            setattr(self, field, getattr(self, field) + amount)

    def record(self, text: str, status: str, reason: str | None = None) -> None:
        with self._lock:
            self.messages.appendleft({"text": text, "status": status, "reason": reason})

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "received": self.received,
                "filtered": self.filtered,
                "parsed": self.parsed,
                "sent": self.sent,
                "rejected": self.rejected,
                "messages": list(self.messages),
            }


# ----------------------------------------------------------------------------
# SignalBot class (kept, with stability fixes: freshness + dedupe)
# ----------------------------------------------------------------------------

class SignalBot:
    """A Telethon-based bot that forwards or copies signals from source channels."""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_string: str,
        from_channels: Iterable[Union[int, str]],
        to_channels: Iterable[Union[int, str]],
        retry_delay: int = 5,
        max_retries: int | None = None,
        profiles: Optional[Dict[str, Dict[Union[int, str], Dict[str, Any]]]] = None,
        routes: Optional[Dict[str, Dict[str, Iterable[Union[int, str]]]]] = None,
        active_profile: str = "default",
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_string = session_string

        # Normalise sources
        norm_from: List[Union[int, str]] = []
        for c in (from_channels or []):
            c = _norm_chat_identifier(c)
            c = _coerce_channel_id(c)
            norm_from.append(c)
        self.from_channels = norm_from

        # Normalise destinations
        norm_to: List[Union[int, str]] = []
        for c in (to_channels or []):
            c = _norm_chat_identifier(c)
            c = _coerce_channel_id(c)
            norm_to.append(c)
        self.to_channels = norm_to

        # Profile mapping (source -> {dests, template})
        self.profiles: Dict[str, Dict[Union[int, str], Dict[str, Any]]] = {}
        if profiles:
            for name, mapping in profiles.items():
                norm_map: Dict[Union[int, str], Dict[str, Any]] = {}
                for src, cfg in (mapping or {}).items():
                    src_norm = _coerce_channel_id(_norm_chat_identifier(src))
                    dests = cfg.get("dests") or []
                    if isinstance(dests, (str, int)):
                        dests = [dests]
                    norm_dests: List[Union[int, str]] = []
                    for d in dests:
                        d = _coerce_channel_id(_norm_chat_identifier(d))
                        norm_dests.append(d)
                    norm_map[src_norm] = {"dests": norm_dests, "template": cfg.get("template")}
                self.profiles[name] = norm_map
        # Routing overrides per profile
        self.routes: Dict[str, Dict[str, List[Union[int, str]]]] = {}
        if routes:
            for name, mapping in routes.items():
                norm_map: Dict[str, List[Union[int, str]]] = {}
                for key, dests in (mapping or {}).items():
                    if isinstance(dests, (str, int)):
                        dests = [dests]
                    norm_dests: List[Union[int, str]] = []
                    for d in dests:
                        d = _coerce_channel_id(_norm_chat_identifier(d))
                        norm_dests.append(d)
                    norm_map[str(key).upper()] = norm_dests
                self.routes[name] = norm_map
        self.active_profile = active_profile

        self.client: Optional[TelegramClient] = None
        self._running = False
        self._callback: Optional[Callable[[dict], None]] = None
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.stats = BotStats()
        
        # freshness/dedupe state
        self.startup_time = datetime.now(timezone.utc)
        self.grace = timedelta(minutes=int(os.environ.get("STARTUP_GRACE_MIN", "2")))  # safe window

        self.fp_window: Deque[Tuple[float, str]] = deque()
        self.fp_set: set[str] = set()
        self.fp_ttl_sec = int(os.environ.get("DEDUP_TTL_SECONDS", "3600"))  # 60 min default

        self.id_window: Deque[Tuple[float, Tuple[int, int]]] = deque()
        self.id_set: set[Tuple[int, int]] = set()
        self.id_ttl_sec = int(os.environ.get("ID_TTL_SECONDS", str(self.fp_ttl_sec)))

    # Callback
    def set_on_signal(self, callback: Optional[Callable[[dict], None]]):
        self._callback = callback

    # Resolve source mapping
    def resolve_targets(self, src_id: Union[int, str]) -> Tuple[List[Union[int, str]], Optional[str]]:
        src_norm = _coerce_channel_id(_norm_chat_identifier(src_id))
        prof = self.profiles.get(self.active_profile, {})
        cfg = prof.get(src_norm)
        if cfg:
            dests = cfg.get("dests") or self.to_channels
            template = cfg.get("template")
            return dests, template
        return self.to_channels, None

    # State
    def is_running(self) -> bool:
        return self._running

    # Stop safely (thread-safe on client loop)
    async def stop(self):
        if self.client:
            try:
                await self.client.disconnect()
                log.info("Client disconnected.")
            except Exception as e:
                log.error(f"Error during disconnect: {e}")
        self._running = False
        
    # Freshness check
    def _fresh_enough(self, ev_dt) -> bool:
        """Process only messages newer than startup (with a small grace window)."""
        if ev_dt is None:
            return True
        if getattr(ev_dt, "tzinfo", None) is None:
            ev_dt = ev_dt.replace(tzinfo=timezone.utc)
        threshold = self.startup_time - self.grace
        if ev_dt < threshold:
            log.debug(
                "Ignoring stale message from %s (startup window %s)",
                ev_dt,
                threshold,
            )
            return False
        return True

    # Dedupe logic
    def _dedup_and_remember(self, src_id: int, msg) -> bool:
        """
        True => already seen (skip).
        Dedupe by (src_id, message_id) and by content fingerprint within TTL window.
        """
        now = time.time()

        while self.id_window and (now - self.id_window[0][0] > self.id_ttl_sec):
            _, old_key = self.id_window.popleft()
            self.id_set.discard(old_key)

        mid = getattr(msg, "id", None)
        if mid is not None:
            key = (int(src_id), int(mid))
            if key in self.id_set:
                log.debug(
                    "Discarding duplicate message id %s from %s", mid, src_id
                )
                return True
            self.id_set.add(key)
            self.id_window.append((now, key))

        while self.fp_window and (now - self.fp_window[0][0] > self.fp_ttl_sec):
            _, old_fp = self.fp_window.popleft()
            self.fp_set.discard(old_fp)

        fp = _content_fingerprint(msg, src_id)
        if fp in self.fp_set:
            log.debug(
                "Discarding duplicate content from %s (fingerprint %s)", src_id, fp
            )
            return True
        self.fp_set.add(fp)
        self.fp_window.append((now, fp))
        return False


    async def _handle_new_message(self, event):
        """Process a new incoming message event."""
        try:
            text = event.message.message or ""
            snippet = text[:160].replace("\n", " ")
            log.info(f"MSG from {event.chat_id}: {snippet} ...")
            self.stats.increment("received")

            if not self._fresh_enough(getattr(event.message, "date", self.startup_time)):
                self.stats.increment("filtered")
                self.stats.record(snippet, "filtered", "stale")
                return

            if self._dedup_and_remember(int(event.chat_id), event.message):
                self.stats.increment("filtered")
                self.stats.record(snippet, "filtered", "duplicate")
                return

            profile = resolve_profile(int(event.chat_id))
            parsed = parse_signal(text, event.chat_id, profile, return_meta=True)
            if not parsed:
                log.info(f"Rejecting message from {event.chat_id}: {snippet}")
                self.stats.increment("rejected")
                self.stats.record(snippet, "rejected", "parse")
                return
            formatted, meta = parsed

            self.stats.increment("parsed")
            dests, template = self.resolve_targets(event.chat_id)

            # Routing overrides based on symbol/position
            symbol = (meta or {}).get("symbol", "")
            position = (meta or {}).get("position", "")
            key = f"{symbol}:{position}".upper()
            route_map = self.routes.get(self.active_profile, {})
            if key in route_map:
                dests = route_map[key]

            if template:
                try:
                    formatted = render_template(template, {"message": formatted})
                except Exception as tmpl_err:
                    log.error(f"Template render failed for {template}: {tmpl_err}")

            sent_any = False
            for dest in dests:
                try:
                    await self.client.send_message(dest, formatted)
                    log.info(f"SENT to {dest}")
                    sent_any = True
                except (ChatWriteForbiddenError, ChatAdminRequiredError) as e:
                    log.error(f"Send failed to {dest} (permissions): {e}")
                except Exception as e:
                    log.warning(f"Send failed to {dest} (will attempt copy): {e}")
                    try:
                        if event.message.media:
                            await self.client.send_file(
                                dest,
                                event.message.media,
                                caption=formatted,
                                force_document=False,
                                allow_cache=False,
                            )
                        else:
                            await self.client.send_message(dest, formatted)
                        log.info(f"COPIED to {dest}")
                        sent_any = True
                    except Exception as copy_err:
                        log.error(f"Copy failed to {dest}: {copy_err}")

            if sent_any:
                self.stats.increment("sent")
                self.stats.record(snippet, "sent")
            else:
                self.stats.increment("rejected")
                self.stats.record(snippet, "rejected", "send")

            if self._callback:
                try:
                    self._callback({"source_chat_id": str(event.chat_id), "text": formatted})
                except Exception:
                    pass
        except Exception as e:
            log.error(f"Handler error: {e}")


    # Start (with auto-reconnect loop)
    async def _run(self):
        if self._running:
            log.info("Bot already running.")
            return
        if not self.session_string:
            log.error("Session string is missing; cannot start bot.")
            return

        self._running = True
        attempts = 0

        while self._running:
            log.info("Connecting...")
            self.client = TelegramClient(StringSession(self.session_string), self.api_id, self.api_hash)

            @self.client.on(events.NewMessage(chats=self.from_channels))
            async def handler(event):
                await self._handle_new_message(event)

            try:
                await self.client.start()

                async def _verify():
                    for c in self.from_channels:
                        try:
                            ent = await self.client.get_entity(c)
                            title = getattr(ent, "title", str(ent))
                            cid = getattr(ent, "id", c)
                            log.info(f"Listening source: {title} (id={cid})")
                        except ChannelPrivateError:
                            log.error(
                                f"Cannot access source '{c}': ChannelPrivateError (not a participant or channel is private)."
                            )
                        except Exception as e:
                            log.error(f"Cannot access source '{c}': {e}")
                    dests_to_check = set(self.to_channels)
                    prof = self.profiles.get(self.active_profile, {})
                    for cfg in prof.values():
                        for d in cfg.get("dests", []):
                            dests_to_check.add(d)
                    for dest in dests_to_check:
                        try:
                            ent = await self.client.get_entity(dest)
                            title = getattr(ent, "title", str(ent))
                            cid = getattr(ent, "id", dest)
                            log.info(f"Destination: {title} (id={cid})")
                        except Exception as e:
                            log.error(f"Cannot access destination '{dest}': {e}")

                await _verify()

                log.info("Bot is up...")
                while self._running:
                    try:
                        await self.client.run_until_disconnected()
                    except (ConnectionError, asyncio.TimeoutError):
                        async def _reconnect():
                            retries = 0
                            while retries < 3 and self._running:
                                try:
                                    await self.client.connect()
                                    return True
                                except (ConnectionError, asyncio.TimeoutError):
                                    retries += 1
                                    if retries >= 3:
                                        return False
                                    await asyncio.sleep(self.retry_delay)

                        if not await _reconnect():
                            log.error("Reconnection attempts failed. Will retry.")
                            break
                        else:
                            log.warning(
                                "Network disconnect detected. Reconnected successfully."
                            )
                            continue
                    else:
                        log.info("Stop requested. Exiting run loop.")
                        break
            except Exception as e:
                log.error(f"Client error: {e}")
            finally:
                if self.client:
                    try:
                        if self._running and await self.client.is_connected():
                            await self.client.disconnect()
                    except Exception:
                        pass

            if not self._running:
                break

            attempts += 1
            if self.max_retries and attempts >= self.max_retries:
                log.error("Max retries reached. Stopping bot.")
                self._running = False
                break

            log.info(f"Reconnecting in {self.retry_delay} seconds...")
            await asyncio.sleep(self.retry_delay)

        self._running = False

    def start(self):
        if self._running:
            return
        try:
            loop = asyncio.get_running_loop()
            self.loop = loop
            loop.create_task(self._run())
            log.info("SignalBot started as background task (web runtime).")
        except RuntimeError:
            log.info("SignalBot running standalone event loop.")
            loop = asyncio.new_event_loop()
            self.loop = loop
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._run())
            finally:
                loop.close()


# ------------------------------------------------------------------------------
# Standalone run (optional)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import json
    api_id = int(os.environ["API_ID"])
    api_hash = os.environ["API_HASH"]
    session_string = os.environ.get("SESSION_STRING", "")
    sources_env = os.environ.get("SOURCES", "[-1001467736193]")
    dest_env = os.environ.get("DESTS", "[\"sjkalalsk\"]")

    try:
        from_channels = json.loads(sources_env)
    except Exception:
        from_channels = []
    try:
        to_channels = json.loads(dest_env)
    except Exception:
        to_channels = []

    bot = SignalBot(
        api_id,
        api_hash,
        session_string,
        from_channels,
        to_channels,
    )
    bot.start()
