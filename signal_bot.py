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
from typing import List, Dict, Optional, Iterable, Callable, Union

from telethon import TelegramClient, events
from telethon.errors import (
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
)

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


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


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
        if any(k in l.lower() for k in TP_KEYS):
            # 1) حالت استاندارد: عدد بلافاصله بعد از "TP" و ":" یا "-"
            found = re.findall(r"(?i)\bTP\s*\d*\s*[:\-]\s*(-?\d+(?:\.\d+)?)", l)
            # 2) حالت "Tp: 3426.00 (400 pips)"
            if not found:
                m = re.search(r"(?i)\btp\b\s*[:\-]\s*(-?\d+(?:\.\d+)?)", l)
                if m:
                    found = [m.group(1)]
            # 3) آخرین راه: حذف برچسب‌های "TP1/TP2/..." و نادیده گرفتن "pips"
            if not found:
                cleaned = re.sub(r"(?i)\bTP\s*\d+\b", "", l)
                # همه‌ی اعداد، به‌جز آنهایی که کنارشان pips آمده
                candidates = re.findall(r"(-?\d+(?:\.\d+)?)", cleaned)
                found = [
                    n for n in candidates
                    if not re.search(rf"{re.escape(n)}\s*(?:pips?)\b", cleaned, re.IGNORECASE)
                ]
            # سقف منطقی و افزودن با حفظ ترتیب
            for n in found[:3]:
                if n not in tps:
                    tps.append(n)
    return tps



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


def to_unified(signal: Dict, chat_id: int, skip_rr_for: Iterable[int] = ()) -> str:
    parts: List[str] = []
    parts.append(f"📊 #{signal['symbol']}")
    parts.append(f"📉 Position: {signal['position']}")
    rr = signal.get("rr")
    if rr and chat_id not in set(skip_rr_for):
        parts.append(f"❗️ R/R : {rr}")
    parts.append(f"💲 Entry Price : {signal['entry']}")
    for i, tp in enumerate(signal["tps"], 1):
        parts.append(f"✔️ TP{i} : {tp}")
    parts.append(f"🚫 Stop Loss : {signal['sl']}")
    return "\n".join(parts)


def parse_signal(text: str, chat_id: int, skip_rr_for: Iterable[int] = ()) -> Optional[str]:
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

    return to_unified(signal, chat_id, skip_rr_for)

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
# SignalBot class (kept, with my stability fixes)
# ----------------------------------------------------------------------------

class SignalBot:
    """A Telethon-based bot that forwards or copies signals from source channels."""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_name: str,
        from_channels: Iterable[Union[int, str]],
        to_channel: Union[int, str],
        skip_rr_chat_ids: Iterable[int] = (),
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_name = session_name

        # Normalise sources
        norm_from: List[Union[int, str]] = []
        for c in (from_channels or []):
            c = _norm_chat_identifier(c)
            c = _coerce_channel_id(c)
            norm_from.append(c)
        self.from_channels = norm_from

        # Normalise destination
        tc = _norm_chat_identifier(to_channel)
        tc = _coerce_channel_id(tc)
        self.to_channel = tc

        self.skip_rr_chat_ids = set(skip_rr_chat_ids)
        self.client: Optional[TelegramClient] = None
        self._running = False
        self._callback: Optional[Callable[[dict], None]] = None

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

    # Start (with event loop fix)
    def start(self):
        if self._running:
            log.info("Bot already running.")
            return

        # Create an event loop for this thread (Telethon needs current loop)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)
        skip_rr_for = self.skip_rr_chat_ids

        @self.client.on(events.NewMessage(chats=self.from_channels))
        async def handler(event):
            """Receive, parse, and forward/copy."""
            try:
                text = event.message.message or ""
                snippet = text[:160].replace("\n", " ")
                log.info(f"MSG from {event.chat_id}: {snippet} ...")

                formatted = parse_signal(text, event.chat_id, skip_rr_for)
                if not formatted:
                    return

                # Try simple text send first
                try:
                    await self.client.send_message(self.to_channel, formatted)
                    log.info(f"SENT to {self.to_channel}")
                except (ChatWriteForbiddenError, ChatAdminRequiredError) as e:
                    log.error(f"Send failed (permissions): {e}")
                except Exception as e:
                    # Fallback: copy media (if any) with caption
                    log.warning(f"Send failed (will attempt copy): {e}")
                    try:
                        if event.message.media:
                            await self.client.send_file(
                                self.to_channel,
                                event.message.media,
                                caption=formatted,
                                force_document=False,
                                allow_cache=False,
                            )
                        else:
                            await self.client.send_message(self.to_channel, formatted)
                        log.info(f"COPIED to {self.to_channel}")
                    except Exception as copy_err:
                        log.error(f"Copy failed: {copy_err}")

                if self._callback:
                    try:
                        self._callback(
                            {"source_chat_id": str(event.chat_id), "text": formatted}
                        )
                    except Exception:
                        pass
            except Exception as e:
                log.error(f"Handler error: {e}")

        self._running = True
        log.info("Starting Telegram client...")
        self.client.start()

        # Verify channels access & log titles/ids
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
            try:
                ent = await self.client.get_entity(self.to_channel)
                title = getattr(ent, "title", str(ent))
                cid = getattr(ent, "id", self.to_channel)
                log.info(f"Destination: {title} (id={cid})")
            except Exception as e:
                log.error(f"Cannot access destination '{self.to_channel}': {e}")

        self.client.loop.run_until_complete(_verify())

        log.info("Client started. Waiting for messages...")
        self.client.run_until_disconnected()
        log.info("Client disconnected (run_until_disconnected returned).")
        self._running = False


# ------------------------------------------------------------------------------
# Standalone run (optional)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import os, json
    api_id = int(os.environ.get("API_ID", "29278288"))
    api_hash = os.environ.get("API_HASH", "8baff9421321d1ef6f14b0511209fbe2")
    session_name = os.environ.get("SESSION_NAME", "signal_bot")
    sources_env = os.environ.get("SOURCES", "[-1001467736193]")
    dest_env = os.environ.get("DEST", "sjkalalsk")

    try:
        from_channels = json.loads(sources_env)
    except Exception:
        from_channels = []

    to_channel = dest_env
    skip_rr_for: set[int] = {1286609636}  # کانال سوم بدون R/R

    bot = SignalBot(
        api_id,
        api_hash,
        session_name,
        from_channels,
        to_channel,
        skip_rr_for,
    )
    bot.start()
