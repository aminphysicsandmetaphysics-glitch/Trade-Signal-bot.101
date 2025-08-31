"""Telethon wrapper for forwarding and parsing trading signals.

This module encapsulates all Telegram interaction.  It normalises
channel identifiers, listens to new messages from a list of source
channels and forwards or copies them to a single destination channel.

When forwarding fails due to content protection, the bot will fall
back to copying the text and any attached media.
"""

from __future__ import annotations

import asyncio
import logging
import re
import os
import time
from dataclasses import dataclass
from collections import deque
from typing import List, Dict, Optional, Iterable, Callable, Union, Deque, Tuple

from telethon.tl.types import InputPeerChannel, MessageMediaPhoto
from telethon.tl.functions.messages import ForwardMessagesRequest
from telethon.errors import (
    MessageIdInvalidError,
    FloodWaitError,
    ChatForwardsRestrictedError,
    SlowModeWaitError,
    MessageAuthorRequiredError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
)
from telethon.sessions import StringSession
from telethon import TelegramClient, events

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("signal-bot")

# ----------------------------------------------------------------------------
# Config helpers
# ----------------------------------------------------------------------------

def env_int(name: str, default: int = 0) -> int:
    try:
        return int(os.environ.get(name, default))
    except Exception:
        return default

def env_list(name: str) -> List[str]:
    v = os.environ.get(name, "")
    return [x.strip() for x in v.split(",") if x.strip()]

# ----------------------------------------------------------------------------
# Signal parsing (REPLACED / IMPROVED)
# ----------------------------------------------------------------------------

# نمادها/سیمبل‌ها
PAIR_RE = re.compile(
    r"(#?\b(?:XAUUSD|XAGUSD|GOLD|SILVER|USOIL|UKOIL|[A-Z]{3,5}[/ ]?[A-Z]{3,5}|[A-Z]{3,5}USD|USD[A-Z]{3,5})\b)"
)
# عدد
NUM_RE = re.compile(r"(-?\d+(?:\.\d+)?)")
# R/R
RR_RE = re.compile(
    r"(\b(?:R\s*/\s*R|Risk[- ]?Reward|Risk\s*:\s*Reward)\b[^0-9]*?(\d+(?:\.\d+)?)\s*[:/]\s*(\d+(?:\.\d+)?))",
    re.IGNORECASE,
)

# --- Profile: UNITED_KINGS (channel 4) ---------------------------------------
# Chat ID(s) of the 4th channel to apply the custom parser for. You can add more ids here.
UNITED_KINGS_CHAT_IDS: set[int] = {-1002223574325}

# Synonyms for side detection in this channel's phrasing
UK_SIDE_SYNONYMS = {
    "buy": re.compile(r"\b(Buy|Grab|Purchase)\b", re.IGNORECASE),
    "sell": re.compile(r"\b(Sell|Unload|Offload|Ditch)\b", re.IGNORECASE),
}

# Range-style entry like: @3411.2-3416.2 (also supports en-dash)
UK_RANGE_RE = re.compile(r"@\s*([0-9]+(?:\.[0-9]+)?)\s*[-–]\s*([0-9]+(?:\.[0-9]+)?)")

# SL/TP variants used by this channel
UK_SL_RES = [
    re.compile(r"\bSL\b\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    re.compile(r"Stop\s*Loss\s*\(SL\)\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    re.compile(r"Set\s*your\s*SL\s*at\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
]
UK_TP1_RES = [
    re.compile(r"\bTP\s*1\b\s*[:：-]\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    re.compile(r"\bTP1\b\s*[:：-]\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    re.compile(r"Take\s*Profit\s*1\s*\(TP1\)\s*[:：-]\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
]
UK_TP2_RES = [
    re.compile(r"\bTP\s*2\b\s*[:：-]\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    re.compile(r"\bTP2\b\s*[:：-]\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    re.compile(r"Take\s*Profit\s*2\s*\(TP2\)\s*[:：-]\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
]

# Lines of boilerplate prose to drop before parsing fields (keeps core signal text)
UK_NOISE_LINES = [
    re.compile(r"(?i)^trade alert.*?:"),
    re.compile(r"(?i)^tyler here.*"),
    re.compile(r"(?i)^alright.*"),
    re.compile(r"(?i)^hey united kings.*"),
    re.compile(r"(?i)^remember,.*"),
    re.compile(r"(?i)^ease in.*"),
    re.compile(r"(?i)^no need.*"),
    re.compile(r"(?i)^keep an eye on these targets:"),
    re.compile(r"(?i)^aiming for take profit at:"),
]

def _clean_uk_lines(text: str) -> list[str]:
    lines = [l.strip() for l in (text or "").splitlines() if l and l.strip()]
    cleaned = []
    for l in lines:
        drop = False
        for rx in UK_NOISE_LINES:
            if rx.search(l):
                drop = True
                break
        if not drop:
            cleaned.append(l)
    return cleaned

def _looks_like_united_kings(text: str) -> bool:
    up = text or ""
    if not re.search(r"\bGold\b", up, re.IGNORECASE):
        return False
    if not UK_RANGE_RE.search(up):
        return False
    if UK_SIDE_SYNONYMS["buy"].search(up) or UK_SIDE_SYNONYMS["sell"].search(up) or re.search(r"\bwe'?re\s+(buying|selling)\b", up, re.IGNORECASE):
        return True
    return False

def parse_signal_united_kings(text: str, chat_id: int, skip_rr_for: Iterable[int] = ()) -> Optional[str]:
    # Drop boilerplate lines to reduce noise
    lines = _clean_uk_lines(text)
    if not lines:
        return None
    raw = "\n".join(lines)

    # Map GOLD → XAUUSD; otherwise try generic symbol guesser
    symbol = "XAUUSD" if re.search(r"\bGOLD\b", raw, re.IGNORECASE) else (guess_symbol(raw) or "")

    # Side from rich verbs
    side = None
    if UK_SIDE_SYNONYMS["buy"].search(raw) or re.search(r"\bwe'?re\s+buying\b", raw, re.IGNORECASE):
        side = "Buy"
    if UK_SIDE_SYNONYMS["sell"].search(raw) or re.search(r"\bwe'?re\s+selling\b", raw, re.IGNORECASE):
        side = "Sell"

    # Entry range (and representative entry for existing downstream sanity checks)
    entry = ""
    entries_extra = None
    rng = UK_RANGE_RE.search(raw)
    if rng:
        lo = float(rng.group(1))
        hi = float(rng.group(2))
        # Keep lower bound as representative entry (consistent with SELL having TPs below, BUY above)
        entry = f"{lo}"
        entries_extra = {"range": [lo, hi]}

    # SL
    sl = ""
    for rx in UK_SL_RES:
        m = rx.search(raw)
        if m:
            sl = m.group(1)
            break

    # TP1/TP2
    tps: list[str] = []
    for rx in UK_TP1_RES:
        m = rx.search(raw)
        if m:
            tps.append(m.group(1))
            break
    for rx in UK_TP2_RES:
        m = rx.search(raw)
        if m:
            tps.append(m.group(1))
            break

    signal = {
        "symbol": symbol or "",
        "position": side or "",
        "entry": entry or "",
        "sl": sl or "",
        "tps": tps,
        "rr": extract_rr(raw) or "",
        "raw": raw,
        "extra": {"entries": entries_extra} if entries_extra else {},
    }

    if not is_valid(signal):
        log.info(f"IGNORED (invalid UK) -> {signal}")
        return None

    # Sanity: TP direction vs entry
    try:
        e = float(entry) if entry else None
        if e is not None and tps:
            if (side or "").upper().startswith("SELL"):
                if all(float(tp) > e for tp in tps):
                    log.info("IGNORED (UK sell but all TP > entry)")
                    return None
            if (side or "").upper().startswith("BUY"):
                if all(float(tp) < e for tp in tps):
                    log.info("IGNORED (UK buy but all TP < entry)")
                    return None
    except Exception:
        pass

    return to_unified(signal, chat_id, skip_rr_for)

# حالت‌های پوزیشن
POS_VARIANTS = [
    ("BUY LIMIT", "Buy Limit"),
    ("SELL LIMIT", "Sell Limit"),
    ("BUY STOP", "Buy Stop"),
    ("SELL STOP", "Sell Stop"),
    ("BUY", "Buy"),
    ("SELL", "Sell"),
]

# کلیدواژه‌های entry/sl/tp
ENTRY_KEYS = ["entry", "entry price", "price", "ورود", "point of entry", "entryzone", "entry zone"]
SL_KEYS = ["sl", "s/l", "stop loss", "استاپ", "حد ضرر"]
TP_KEYS = ["tp", "target", "take profit", "حد سود", " تارگت"]

def normalize_numbers(text: str) -> str:
    # تبدیل ارقام فارسی/عربی به انگلیسی + استانداردسازی جداکننده اعشار
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٬،", "01234567890123456789..")
    return (text or "").translate(trans)

def guess_symbol(text: str) -> Optional[str]:
    m = PAIR_RE.search(text or "")
    if not m:
        return None
    sym = m.group(1).upper().replace(" ", "").replace("/", "")
    # GOLD و SILVER به XAUUSD/XAGUSD نگاشت شوند
    if sym in ("GOLD", "#GOLD"):
        return "XAUUSD"
    if sym in ("SILVER", "#SILVER"):
        return "XAGUSD"
    return sym.lstrip("#")

def guess_position(text: str) -> Optional[str]:
    up = (text or "").upper()
    for raw, norm in POS_VARIANTS:
        if raw in up:
            return norm
    if re.search(r"\bBUY\b", up):
        return "Buy"
    if re.search(r"\bSELL\b", up):
        return "Sell"
    return None


def extract_entry(lines: List[str]) -> Optional[str]:
    # حالت‌های صریح Entry
    for l in lines:
        if any(k in l.lower() for k in ENTRY_KEYS):
            m = re.search(NUM_RE, l)
            if m:
                return m.group(1)

    # BUY/SELL در ابتدای خط + عدد
    for l in lines:
        m = re.search(r'\b(?:BUY|SELL)\b[^\d\-+]*(-?\d+(?:\.\d+)?)', l, re.IGNORECASE)
        if m:
            return m.group(1)

    # عددی که در خطی آمده که در آن symbol و position دیده می‌شود
    for l in lines:
        if PAIR_RE.search(l):
            m = re.search(NUM_RE, l)
            if m:
                return m.group(1)

    # fallback: اولین عدد معقول
    for l in lines:
        m = re.search(NUM_RE, l)
        if m:
            return m.group(1)
    return None

def extract_sl(lines: List[str]) -> Optional[str]:
    for l in lines:
        if any(k in l.lower() for k in SL_KEYS):
            m = re.search(NUM_RE, l)
            if m:
                return m.group(1)
    # کلمات S/L یا stop در یک خط
    for l in lines:
        m = re.search(r'\bS/?L\b[^\d\-+]*(-?\d+(?:\.\d+)?)', l, re.IGNORECASE)
        if m:
            return m.group(1)
    for l in lines:
        m = re.search(r'\bstop\s*loss\b[^\d\-+]*(-?\d+(?:\.\d+)?)', l, re.IGNORECASE)
        if m:
            return m.group(1)
    return None

def extract_tps(lines: List[str]) -> List[str]:
    tps: List[str] = []

    # حالت‌های صریح TPn: value
    for l in lines:
        m = re.search(r'\bTP\s*\d*\s*[:\-]\s*(-?\d+(?:\.\d+)?)', l, re.IGNORECASE)
        if m:
            tps.append(m.group(1))
            continue

        # 2) در غیر این صورت، اولین عددی را بگیر که تا 6 کاراکتر بعدش "pip/pips" نیامده
        #    (تا «80 pips» به‌عنوان TP شمرده نشود) و عددهای خیلی کوچکِ شاخص (مثل "1" در "TP1") حذف شوند.
        for nm in re.finditer(r'(-?\d+(?:\.\d+)?)(?![^\n]{0,6}\s*pips?\b)', l, re.IGNORECASE):
            num = nm.group(1)

            # اگر خط شامل TP بود، اعداد خیلی کوچک و بدون اعشار (شماره TP) را رد کن
            if re.search(r'\bTP\b', l, re.IGNORECASE) and re.fullmatch(r'\d+', num):
                # معمولاً شماره‌های TP کوچک‌اند؛ ردش کن
                if int(num) <= 10:
                    continue

            tps.append(num)

    # یکتا سازی و محدود به 4 تارگت
    uniq: List[str] = []
    for x in tps:
        if x not in uniq:
            uniq.append(x)
    return uniq[:4]

def extract_rr(text: str) -> Optional[str]:
    m = RR_RE.search(text or "")
    if not m:
        return None
    # m.group(1) الگوی کامل، 2 و 3 اعداد
    return f"{m.group(2)}:{m.group(3)}"

def looks_like_update(text: str) -> bool:
    up = (text or "").lower()
    # پیام‌های نتیجه/آپدیت/تبلیغ
    if any(k in up for k in ["result", "results", "report", "pnl", "closed", "hit tp", "hit sl", "giveaway", "promotion"]):
        return True
    # پیام‌های خیلی کوتاه یا ایموجی صرف
    if len(up) < 8:
        return True
    return False

def is_valid(signal: Dict) -> bool:
    # باید position، entry، sl و حداقل یک TP داشته باشیم
    if not signal.get("position") or not signal.get("entry") or not signal.get("sl"):
        return False
    if not signal.get("tps"):
        return False
    # نماد
    sym = signal.get("symbol", "")
    if not sym:
        return False
    return True

def to_unified(signal: Dict, chat_id: int, skip_rr_for: Iterable[int] = ()) -> str:
    parts: List[str] = []
    parts.append(f"📊 #{signal['symbol']}")
    parts.append(f"📉 Position: {signal['position']}")
    rr = signal.get("rr")
    if rr and chat_id not in set(skip_rr_for):
        parts.append(f"❗️ R/R : {rr}")
    parts.append(f"💲 Entry Price : {signal['entry']}")
    # Optional entry range for profiles that provide it (non-breaking for others)
    try:
        rng = signal.get('extra', {}).get('entries', {}).get('range')
        if rng and isinstance(rng, (list, tuple)) and len(rng) == 2:
            parts.append(f"🎯 Entry Range : {rng[0]} – {rng[1]}")
    except Exception:
        pass
    for i, tp in enumerate(signal["tps"], 1):
        parts.append(f"✔️ TP{i} : {tp}")
    parts.append(f"🚫 Stop Loss : {signal['sl']}")
    return "\n".join(parts)


def parse_signal(text: str, chat_id: int, skip_rr_for: Iterable[int] = ()) -> Optional[str]:
    # حذف پیام‌های غیرسیگنال (آپدیت/تبلیغ/نتیجه)
    if looks_like_update(text):
        log.info("IGNORED (update/noise)")
        return None

    # Channel-4 specialised parser (United Kings VIP)
    try:
        if (chat_id in UNITED_KINGS_CHAT_IDS) or _looks_like_united_kings(text):
            res = parse_signal_united_kings(text, chat_id, skip_rr_for)
            if res:
                return res
    except Exception:
        # Fail open to generic parser
        pass

    lines = [l.strip() for l in (text or "").splitlines() if l and l.strip()]
    if not lines:
        log.info("IGNORED (empty)")
        return None

    symbol = guess_symbol(text) or ""
    position = guess_position(text) or ""
    entry = extract_entry(lines) or ""
    sl = extract_sl(lines) or ""
    tps = extract_tps(lines)

    # RR
    rr = extract_rr(text) or ""

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

    # sanity check: جهت TPها با Entry همخوان باشد
    try:
        e = float(entry)
        if position.upper().startswith("SELL"):
            if all(float(tp) > e for tp in tps):
                log.info("IGNORED (sell but all TP > entry)")
                return None
        if position.upper().startswith("BUY"):
            if all(float(tp) < e for tp in tps):
                log.info("IGNORED (buy but all TP < entry)")
                return None
    except Exception:
        pass

    return to_unified(signal, chat_id, skip_rr_for)

# ----------------------------------------------------------------------------
# Telethon wrapper (forward/copy)
# ----------------------------------------------------------------------------

@dataclass
class ChannelRef:
    id: Union[int, str]
    name: str

def _content_fingerprint(msg, src_id: Union[int, str]) -> str:
    """A stable fingerprint for deduplicating messages across reconnects."""
    body = (msg.message or "").strip()
    date = int(getattr(msg, "date", 0).timestamp()) if getattr(msg, "date", None) else 0
    return f"{src_id}|{date}|{hash(body)}|{len(getattr(msg, 'media', b''))}"

class RateLimiter:
    """Simple token-bucket to avoid FloodWait for copy mode."""
    def __init__(self, rate: float, burst: int):
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.updated = time.monotonic()

    def acquire(self) -> None:
        now = time.monotonic()
        elapsed = now - self.updated
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.updated = now
        if self.tokens < 1:
            # sleep until we have 1 token
            wait = (1 - self.tokens) / self.rate
            time.sleep(max(0.05, wait))
            self.tokens = 0
            self.updated = time.monotonic()
        self.tokens -= 1

class FreshDedupe:
    """Deduplicate messages in a sliding window to avoid double-forward."""
    def __init__(self, ttl_sec: int = 90):
        self.fp_set: set[str] = set()
        self.fp_window: Deque[Tuple[float, str]] = deque()
        self.fp_ttl_sec = ttl_sec

    def seen(self, msg, src_id: Union[int, str]) -> bool:
        now = time.monotonic()
        while self.fp_window and (now - self.fp_window[0][0] > self.fp_ttl_sec):
            _, old_fp = self.fp_window.popleft()
            self.fp_set.discard(old_fp)

        fp = _content_fingerprint(msg, src_id)
        if fp in self.fp_set:
            return True
        self.fp_set.add(fp)
        self.fp_window.append((now, fp))
        return False


# ----------------------------------------------------------------------------
# Entrypoint utilities
# ----------------------------------------------------------------------------

def parse_source_list(val: str) -> List[Union[int, str]]:
    xs = []
    for p in (val or "").split(","):
        p = p.strip()
        if not p:
            continue
        try:
            xs.append(int(p))
        except Exception:
            xs.append(p)
    return xs

def _coerce_channel_id(x: Union[int, str]) -> Union[int, str]:
    """Coerce positive numeric IDs to Telegram channel form -100XXXXXXXXXX."""
    if isinstance(x, int):
        return x if x < 0 else int("-100" + str(x))
    return x


# ----------------------------------------------------------------------------
# SignalBot class (with stability fixes: freshness + dedupe)
# ----------------------------------------------------------------------------

class SignalBot:
    """A Telethon-based bot that forwards or copies signals from source channels."""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        string_session: str,
        sources: List[Union[int, str]],
        sink: Union[int, str],
        copy_if_protected: bool = True,
        skip_rr_for: Iterable[int] = (),
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.string_session = string_session
        self.sources = [self._normalize_channel_id(x) for x in sources]
        self.sink = self._normalize_channel_id(sink)
        self.copy_if_protected = copy_if_protected
        self.skip_rr_for = set(skip_rr_for)

        self._running = False
        self._client = None
        self._dedupe = FreshDedupe(ttl_sec=120)
        self._copy_rate = RateLimiter(rate=1.5, burst=3)

    # Normalise channel id to Telegram format -100XXXXXXXXXX
    def _normalize_channel_id(self, x: Union[int, str]) -> Union[int, str]:
        if isinstance(x, int):
            return x if x < 0 else int("-100" + str(x))
        try:
            xi = int(x)
            return xi if xi < 0 else int("-100" + str(xi))
        except Exception:
            return x

    # Public getter (optional)
    @property
    def running(self) -> bool:
        return self._running

    # Run loop
    async def _run(self):
        session = StringSession(self.string_session)
        client = TelegramClient(session, self.api_id, self.api_hash)
        await client.connect()
        self._client = client

        @client.on(events.NewMessage(chats=self.sources))
        async def handler(event):
            try:
                if self._dedupe.seen(event.message, event.chat_id):
                    log.debug("Duplicate ignored (sliding window)")
                    return

                raw_text = normalize_numbers(event.message.message or "")
                parsed = parse_signal(raw_text, event.chat_id, self.skip_rr_for)
                if not parsed:
                    log.info("No valid signal parsed; skipping.")
                    return

                try:
                    # Attempt direct forward first
                    await client(ForwardMessagesRequest(
                        from_peer=event.message.to_id,
                        id=[event.message.id],
                        to_peer=self.sink,
                        with_my_score=False,
                        drop_author=True,
                    ))
                    log.info("Forwarded message (native forward).")
                except (ChatForwardsRestrictedError, ChatAdminRequiredError, MessageAuthorRequiredError, ChannelPrivateError):
                    if not self.copy_if_protected:
                        log.warning("Forward restricted and copy mode disabled; skipping.")
                        return
                    # Copy mode (text + photo if exists)
                    await self._copy_message(client, event, parsed)
                    log.info("Copied message (fallback).")

            except FloodWaitError as fw:
                log.warning(f"Flood wait: {fw.seconds}s; pausing handler.")
                await asyncio.sleep(min(5, fw.seconds))
            except SlowModeWaitError as sw:
                log.warning(f"Slow mode: {sw.seconds}s; delaying send.")
                await asyncio.sleep(min(5, sw.seconds))
            except ChatWriteForbiddenError:
                log.error("Cannot write to sink channel (forbidden).")
            except Exception as e:
                log.exception(f"Unhandled in handler: {e}")

        log.info("Bot is up; listening to sources.")
        await client.run_until_disconnected()

    async def _copy_message(self, client, event, parsed_text: str):
        self._copy_rate.acquire()
        # send parsed text; attach photo if original had one
        media = None
        if isinstance(event.message.media, MessageMediaPhoto):
            media = event.message.media
        await client.send_message(self.sink, parsed_text, file=media, link_preview=False)

    # Start (with auto-reconnect loop)
    def start(self):
        if self._running:
            return
        self._running = True
        while True:
            try:
                asyncio.run(self._run())
            except KeyboardInterrupt:
                log.info("Interrupted by user.")
                break
            except Exception as e:
                log.exception(f"Fatal in main loop; restarting in 5s: {e}")
                time.sleep(5)
