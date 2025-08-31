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
import hashlib
import time
from datetime import datetime, timezone, timedelta
from collections import deque
from typing import List, Dict, Optional, Iterable, Callable, Union, Deque, Tuple

from telethon import TelegramClient, events
from telethon.errors import (
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
)
from telethon.sessions import StringSession

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("signal-bot")

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
NON_SIGNAL_HINTS = [
    "activated", "tp reached", "result so far", "screenshots", "cheers", "high-risk setup",
    "move sl", "put your sl", "risk free", "close", "closed", "delete", "running",
    "trade - update", "update", "guide", "watchlist", "broker", "subscription", "contact", "admin",
    "tp almost", "tp hit", "tp reached", "sl reached", "sl hit", "profits", "week", "friday",
]

TP_KEYS = ["tp", "take profit", "take-profit", "t/p", "t p"]
SL_KEYS = ["sl", "stop loss", "stop-loss", "s/l", "s l"]
ENTRY_KEYS = ["entry price", "entry", "e:"]

# Special-case parsing for the "United Kings" channels
# (IDs taken from known public channels)
UNITED_KINGS_CHAT_IDS = {
    -1001709190364,
    -1001642415461,
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def normalize_numbers(text: str) -> str:
    """Translate Persian/Arabic digits and separators to ASCII equivalents."""
    if not text:
        return ""

    # Map Eastern Arabic and Persian digits to Western Arabic numerals
    trans = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
    trans.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})

    # Normalize decimal and thousands separators
    trans[ord("٫")] = "."  # Arabic decimal separator
    trans[ord("٬")] = ""  # Arabic thousands separator (remove)

    return text.translate(trans)


def guess_symbol(text: str) -> Optional[str]:
    m = PAIR_RE.search((text or "").upper())
    if not m:
        return None
    sym = m.group(1).upper().lstrip("#").replace(" ", "").replace("/", "")
    if sym == "GOLD":
        sym = "XAUUSD"
    return sym


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
            m = NUM_RE.search(l)
            if m:
                return m.group(1)
    # حالت فشرده مثل: "BUY 3373.33" یا "SELL LIMIT 3338"
    for l in lines:
        if re.search(r"\b(BUY|SELL)(?:\s+(LIMIT|STOP))?\s+(-?\d+(?:\.\d+)?)\b", l, re.IGNORECASE):
            m = re.search(r"(-?\d+(?:\.\d+)?)", l)
            if m:
                return m.group(1)
    return None


def extract_sl(lines: List[str]) -> Optional[str]:
    for l in lines:
        if any(k in l.lower() for k in SL_KEYS):
            m = NUM_RE.search(l)
            if m:
                return m.group(1)
    return None


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


def looks_like_update(text: str) -> bool:
    t = (text or "").lower()
    return any(key in t for key in NON_SIGNAL_HINTS)


def is_valid(signal: Dict) -> bool:
    return all([
        signal.get("symbol"),
        signal.get("position"),
        signal.get("entry"),
        signal.get("sl"),
    ]) and len(signal.get("tps", [])) >= 1


def to_unified(
    signal: Dict,
    chat_id: int,
    skip_rr_for: Iterable[int] = (),
    extra: Optional[Dict] = None,
) -> str:
    extra = extra if extra is not None else signal.get("extra", {})

    parts: List[str] = []
    parts.append(f"📊 #{signal['symbol']}")
    parts.append(f"📉 Position: {signal['position']}")
    rr = signal.get("rr")
    if rr and chat_id not in set(skip_rr_for):
        parts.append(f"❗️ R/R : {rr}")
    parts.append(f"💲 Entry Price : {signal['entry']}")
    
    entry_range = extra.get("entries", {}).get("range")
    if entry_range:
        try:
            lo, hi = entry_range
            parts.append(f"🎯 Entry Range : {lo} – {hi}")
        except Exception:
            pass

    for i, tp in enumerate(signal["tps"], 1):
        parts.append(f"✔️ TP{i} : {tp}")
    parts.append(f"🚫 Stop Loss : {signal['sl']}")
    return "\n".join(parts)


def _clean_uk_lines(text: str) -> List[str]:
    """Normalise and trim United Kings signal lines."""
    lines: List[str] = []
    for raw in (text or "").splitlines():
        raw = raw.strip()
        raw = re.sub(r"^[\-•\s]+", "", raw)
        if raw:
            lines.append(raw)
    return lines


def _looks_like_united_kings(text: str) -> bool:
    """Heuristic check for United Kings style messages."""
    lines = _clean_uk_lines(text)
    joined = " ".join(lines).lower()
    if "united" in joined and "king" in joined:
        return True
    return any("tp" in l.lower() for l in lines) and any("sl" in l.lower() for l in lines)


def parse_signal_united_kings(
    text: str, chat_id: int, skip_rr_for: Iterable[int] = ()
) -> Optional[str]:
    if looks_like_update(text):
        log.info("IGNORED (update/noise)")
        return None

    lines = _clean_uk_lines(text)
    if not lines:
        log.info("IGNORED (empty)")
        return None

    symbol = guess_symbol(text) or ""
    position = guess_position(text) or ""
    entry = extract_entry(lines) or ""
    sl = extract_sl(lines) or ""
    tps = extract_tps(lines)
    rr = extract_rr(text)

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

    return to_unified(signal, chat_id, skip_rr_for)


def parse_channel_four(
    text: str, chat_id: int, skip_rr_for: Iterable[int] = ()
) -> Optional[str]:
    """Parser for Channel Four style messages supporting entry ranges."""
    if looks_like_update(text):
        log.info("IGNORED (update/noise)")
        return None

    lines = [l.strip() for l in (text or "").splitlines() if l and l.strip()]
    if not lines:
        log.info("IGNORED (empty)")
        return None

    symbol = guess_symbol(text) or ""
    position = guess_position(text) or ""
    entry = extract_entry(lines) or ""
    sl = extract_sl(lines) or ""
    tps = extract_tps(lines)
    rr = extract_rr(text)

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

    return to_unified(signal, chat_id, skip_rr_for, signal.get("extra", {}))

def parse_signal(text: str, chat_id: int, skip_rr_for: Iterable[int] = ()) -> Optional[str]:
    text = normalize_numbers(text)
    # Special-case: United Kings parser (if available)
    uk_ids: set[int] = set()
    looks_uk = None
    parse_uk = None
    try:
        uk_ids = set(globals().get("UNITED_KINGS_CHAT_IDS", []))
        looks_uk = globals().get("_looks_like_united_kings")
        parse_uk = globals().get("parse_signal_united_kings")
    except Exception as e:
        log.debug(f"United Kings parser failed: {e}")

    if parse_uk and (chat_id in uk_ids or (looks_uk and looks_uk(text))):
        try:
            res = parse_uk(text, chat_id, skip_rr_for)
            if res is not None:
                return res
        except Exception as e:
            log.debug(f"United Kings parser failed: {e}")

    # حذف پیام‌های غیرسیگنال (آپدیت/تبلیغ/نتیجه)
    if looks_like_update(text):
        log.info("IGNORED (update/noise)")
        return None

    lines = [l.strip() for l in (text or "").splitlines() if l and l.strip()]
    if not lines:
        log.info("IGNORED (empty)")
        return None

    symbol = guess_symbol(text) or ""
    position = guess_position(text) or ""
    entry = extract_entry(lines) or ""
    sl = extract_sl(lines) or ""
    tps = extract_tps(lines)
    rr = extract_rr(text)

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

    return to_unified(signal, chat_id, skip_rr_for, signal.get("extra", {}))

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
        return x
    s = (x or "").strip()
    s = re.sub(r"^https?://t\.me/", "", s, flags=re.IGNORECASE)
    s = s.lstrip("@").strip()
    return s


def _coerce_channel_id(x: Union[int, str]) -> Union[int, str]:
    """Coerce positive numeric IDs to Telegram channel form -100XXXXXXXXXX."""
    if isinstance(x, int):
        return x if x < 0 else int("-100" + str(x))
    return x


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
        skip_rr_chat_ids: Iterable[int] = (),
        retry_delay: int = 5,
        max_retries: int | None = None,
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

        self.skip_rr_chat_ids = set(skip_rr_chat_ids)
        self.client: Optional[TelegramClient] = None
        self._running = False
        self._callback: Optional[Callable[[dict], None]] = None
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        
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

    # State
    def is_running(self) -> bool:
        return self._running

    # Stop safely (thread-safe on client loop)
    def stop(self):
        if self.client:
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    self.client.disconnect(), self.client.loop
                )
                fut.result(timeout=10)
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
        return ev_dt >= (self.startup_time - self.grace)

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
                return True
            self.id_set.add(key)
            self.id_window.append((now, key))

        while self.fp_window and (now - self.fp_window[0][0] > self.fp_ttl_sec):
            _, old_fp = self.fp_window.popleft()
            self.fp_set.discard(old_fp)

        fp = _content_fingerprint(msg, src_id)
        if fp in self.fp_set:
            return True
        self.fp_set.add(fp)
        self.fp_window.append((now, fp))
        return False


    # Start (with auto-reconnect loop)
    def start(self):
        if self._running:
            log.info("Bot already running.")
            return
        if not self.session_string:
            log.error("Session string is missing; cannot start bot.")
            return
    
        self._running = True
        attempts = 0

        while self._running:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.client = TelegramClient(StringSession(self.session_string), self.api_id, self.api_hash)
            skip_rr_for = self.skip_rr_chat_ids

            @self.client.on(events.NewMessage(chats=self.from_channels, incoming=True))
            async def handler(event):
                """Receive, parse, and forward/copy."""
                try:
                    text = event.message.message or ""
                    text = normalize_numbers(text)
                    snippet = text[:160].replace("\n", " ")
                    log.info(f"MSG from {event.chat_id}: {snippet} ...")
                    
                    if not self._fresh_enough(getattr(event.message, "date", self.startup_time)):
                        return

                    if self._dedup_and_remember(int(event.chat_id), event.message):
                        return

                    formatted = parse_signal(text, event.chat_id, skip_rr_for)
                    if not formatted:
                        return

                    for dest in self.to_channels:
                        try:
                            await self.client.send_message(dest, formatted)
                            log.info(f"SENT to {dest}")
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
                            except Exception as copy_err:
                                log.error(f"Copy failed to {dest}: {copy_err}")

                    if self._callback:
                        try:
                            self._callback({"source_chat_id": str(event.chat_id), "text": formatted})
                        except Exception:
                            pass
                except Exception as e:
                    log.error(f"Handler error: {e}")

            log.info("Starting Telegram client...")
            try:
                self.client.start()

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
                    for dest in self.to_channels:
                        try:
                            ent = await self.client.get_entity(dest)
                            title = getattr(ent, "title", str(ent))
                            cid = getattr(ent, "id", dest)
                            log.info(f"Destination: {title} (id={cid})")
                        except Exception as e:
                            log.error(f"Cannot access destination '{dest}': {e}")

                self.client.loop.run_until_complete(_verify())

                log.info("Client started. Waiting for messages...")
                while self._running:
                    try:
                        self.client.run_until_disconnected()
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

                        if not self.client.loop.run_until_complete(_reconnect()):
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
                        # Only disconnect here if stop() hasn't already done so via
                        # asyncio.run_coroutine_threadsafe.
                        if (
                            self._running
                            and self.client.loop.run_until_complete(self.client.is_connected())
                        ):
                            self.client.loop.run_until_complete(self.client.disconnect())
                    except Exception:
                        pass
                loop.close()

            if not self._running:
                break

            attempts += 1
            if self.max_retries and attempts >= self.max_retries:
                log.error("Max retries reached. Stopping bot.")
                self._running = False
                break

            log.info(f"Reconnecting in {self.retry_delay} seconds...")
            time.sleep(self.retry_delay)

        self._running = False


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

    skip_rr_for: set[int] = {1286609636}  # کانال سوم بدون R/R

    bot = SignalBot(
        api_id,
        api_hash,
        session_string,
        from_channels,
        to_channels,
        skip_rr_for,
    )
    bot.start()
