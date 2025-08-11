from __future__ import annotations
import asyncio, logging, re, unicodedata
from typing import List, Dict, Optional, Callable, Iterable, Union

from telethon import TelegramClient, events
from telethon.errors import (
    ChannelPrivateError, ChatAdminRequiredError, ChatWriteForbiddenError
)
from telethon.errors.rpcerrorlist import FloodWaitError

# ---------------------- Logging ----------------------
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("signal-bot")

# ---------------------- Normalization helpers ----------------------

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_ARABIC_DIGITS  = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def normalize_text(s: str | None) -> str:
    """ Unicode NFKC + trim + unify colon + remove zero-width + normalize digits + normalize spaces """
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    # remove zero-width chars
    s = re.sub(r"[\u200b\u200c\u200d\u2060]", "", s)
    # digits
    s = s.translate(_PERSIAN_DIGITS).translate(_ARABIC_DIGITS)
    # unify colon variants to ':'
    s = s.replace("：", ":")
    # unify dashes and spaces
    s = re.sub(r"[‐‑‒–—]", "-", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def split_lines(raw: str) -> List[str]:
    if not raw:
        return []
    # keep original line boundaries for key-value scanning
    txt = raw.replace("\r\n", "\n").replace("\r", "\n")
    # also normalize digits etc. line-wise later
    return [l.strip() for l in txt.split("\n") if l.strip()]

def to_float_str(num: str) -> Optional[str]:
    if not num:
        return None
    n = num.strip().replace(",", ".")
    try:
        float(n)
        # format with up to 5 decimals, but keep original significant decimals
        # If integer-like, keep .00 style only if provided? We keep normalized as-is.
        # For consistent printing, we show original precision if it had decimals,
        # else keep integer .00? We'll standardize to show what author used.
        # Here return n as-is (already dot decimal).
        return n
    except Exception:
        return None

# ---------------------- Signal Parsing ----------------------

# Accept symbols from hashtags or pair-like tokens; do NOT map/rename (user request).
HASHTAG_SYM = re.compile(r"#([A-Za-z0-9_./-]{2,20})")
PAIR_RE     = re.compile(r"\b([A-Z]{3,5}[/]?[A-Z]{3,5}|GOLD|SILVER|USOIL|UKOIL|WTI|BRENT)\b", re.IGNORECASE)

# Position / Type
POS_RE = re.compile(
    r"(?i)\b(?:(BUY|SELL)\s*(LIMIT|STOP)?|(LONG|SHORT))\b"
)

# Numbers (float/int; dot or comma)
NUM_RE = re.compile(r"(-?\d+(?:[.,]\d{1,5})?)")

# Canonical keys (case-insensitive)
ENTRY_KEYS = re.compile(r"(?i)\b(entry(?:\s*price)?|^E[:=])\b")
SL_KEYS    = re.compile(r"(?i)\b(sl|stop\s*loss|stop)\b")
TP_KEYS    = re.compile(r"(?i)\b(tp\d*|take\s*profit|t/p|t\s*p)\b")

# Risk/Reward: captures like "1/3", "1 : 2.5", "R/R 1:4"
RR_RE = re.compile(
    r"(?i)\b(?:R\s*/\s*R|Risk\s*[-/:]?\s*Reward|R\s*[:/])[^0-9]*?(\d+(?:[.,]\d{1,5})?)\s*[:/]\s*(\d+(?:[.,]\d{1,5})?)\b"
)

# Noise / updates to filter out (don’t send)
NOISE_HINTS = re.compile(
    r"(?i)\b(activated|update|result\s+so\s+far|watchlist|broker|subscription|contact|admin|giveaway|rules|join\s+channel|news)\b"
)

def first_symbol(text: str) -> Optional[str]:
    # Prefer hashtag symbol like #XAUUSD
    m = HASHTAG_SYM.search(text)
    if m:
        return m.group(1).upper()

    # Else try pair-like token (no mapping, keep as is upper)
    m = PAIR_RE.search(text)
    if m:
        return m.group(1).upper().replace("/", "")
    return None

def find_position(text: str) -> Optional[str]:
    m = POS_RE.search(text)
    if not m:
        return None
    buy_sell, limstop, long_short = m.group(1), m.group(2), m.group(3)
    if long_short:
        return "BUY" if long_short.upper() == "LONG" else "SELL"
    if buy_sell:
        base = buy_sell.upper()
        if limstop:
            return f"{base} {limstop.title()}"
        return base
    return None

def extract_entry(lines: List[str], text: str) -> Optional[str]:
    # Line with Entry key
    for l in lines:
        if ENTRY_KEYS.search(l):
            m = NUM_RE.search(l)
            if m:
                return to_float_str(m.group(1))
    # Pattern like: BUY LIMIT 3350  or  SELL 1.2345
    m = re.search(r"(?i)\b(?:BUY|SELL)(?:\s+(?:LIMIT|STOP))?\s+(-?\d+(?:[.,]\d{1,5})?)\b", text)
    if m:
        return to_float_str(m.group(1))
    return None

def extract_sl(lines: List[str]) -> Optional[str]:
    for l in lines:
        if SL_KEYS.search(l):
            m = NUM_RE.search(l)
            if m:
                return to_float_str(m.group(1))
    return None

def extract_tps(lines: List[str], text: str) -> List[str]:
    tps: List[str] = []
    # lines like "TP1: 3305", "TP: 3305", "TP 1 3305"
    for l in lines:
        if TP_KEYS.search(l):
            nums = NUM_RE.findall(l)
            for n in nums:
                s = to_float_str(n)
                if s:
                    tps.append(s)
    # If none found, try a fallback single-line "TP 3400" in whole text
    if not tps:
        m = re.search(r"(?i)\bTP[:\s]+(-?\d+(?:[.,]\d{1,5})?)\b", text)
        if m:
            s = to_float_str(m.group(1))
            if s:
                tps.append(s)
    # de-dup keep order
    seen = set()
    ordered = []
    for x in tps:
        if x not in seen:
            seen.add(x)
            ordered.append(x)
    return ordered

def extract_rr(text: str) -> Optional[str]:
    m = RR_RE.search(text)
    if not m:
        return None
    a = to_float_str(m.group(1))
    b = to_float_str(m.group(2))
    if a and b:
        # print as A/B with original decimals
        return f"{a}/{b}"
    return None

def validate_signal(symbol: Optional[str], position: Optional[str],
                    entry: Optional[str], sl: Optional[str], tps: List[str]) -> bool:
    # Require minimal fields to avoid false positives
    if not (symbol and position and entry and sl):
        return False
    if not tps:
        return False
    # sanity check directions
    try:
        e = float(entry)
        slv = float(sl)
        tpf = [float(x) for x in tps]
        pos = position.upper()
        if "SELL" in pos:
            # for SELL: SL should be > entry in most cases; TPs < entry
            if not all(tp <= e or abs(tp - e) < 1e-9 for tp in tpf):
                return False
        if "BUY" in pos:
            # for BUY: SL should be < entry; TPs > entry
            if not all(tp >= e or abs(tp - e) < 1e-9 for tp in tpf):
                return False
    except Exception:
        pass
    return True

def format_output(symbol: str, position: str, entry: str, sl: str,
                  tps: List[str], rr: Optional[str], skip_rr_for: Iterable[int], chat_id: int) -> str:
    lines = []
    lines.append(f"📊 #{symbol}")
    lines.append(f"📉 Position: {position.upper()}")
    if rr and (chat_id not in set(skip_rr_for)):
        # user wants "❗️ R/R : 1/4", our rr is "1/4" or "1.0/4.0"
        lines.append(f"❗️ R/R : {rr}")
    lines.append(f"💲 Entry Price : {entry}")
    if len(tps) == 1:
        lines.append(f"✔️ TP : {tps[0]}")
    else:
        for i, tp in enumerate(tps, 1):
            lines.append(f"✔️ TP{i} : {tp}")
    lines.append(f"🚫 Stop Loss : {sl}")
    return "\n".join(lines)

def parse_signal(text: str, chat_id: int, skip_rr_for: Iterable[int] = ()) -> Optional[str]:
    """
    Drop-in parser used by app.py -> SignalBot handler.
    Returns formatted text or None.
    """
    if not text or NOISE_HINTS.search(text):
        return None

    raw_lines = split_lines(text)
    norm_text = normalize_text(text)
    lines = split_lines(norm_text)

    # Extract fields
    symbol = first_symbol(norm_text)
    position = find_position(norm_text)
    entry = extract_entry(lines, norm_text)
    sl = extract_sl(lines)
    tps = extract_tps(lines, norm_text)
    rr = extract_rr(norm_text)

    # Validate
    if not validate_signal(symbol, position, entry, sl, tps):
        log.info(f"IGNORED (not a valid signal) -> sym={symbol}, pos={position}, entry={entry}, sl={sl}, tps={tps}")
        return None

    # Format
    return format_output(symbol, position, entry, sl, tps, rr, skip_rr_for, chat_id)

# ---------------------- Channel normalization ----------------------

def _norm_chat_identifier(x: Union[int, str]) -> Union[int, str]:
    if isinstance(x, int):
        return x
    s = (x or "").strip()
    s = re.sub(r"^https?://t\.me/", "", s, flags=re.IGNORECASE)
    s = s.lstrip("@").strip()
    return s

def _coerce_channel_id(x: Union[int, str]) -> Union[int, str]:
    if isinstance(x, int):
        return x if x < 0 else int("-100" + str(x))
    return x

# ---------------------- Bot Class ----------------------

class SignalBot:
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_name: str,
        from_channels,
        to_channel,
        skip_rr_chat_ids: Iterable[int] = ()
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_name = session_name

        # Normalize inputs
        norm_from = []
        for c in (from_channels or []):
            c = _norm_chat_identifier(c)
            c = _coerce_channel_id(c)
            norm_from.append(c)
        self.from_channels = norm_from
        self.to_channel = _norm_chat_identifier(to_channel)

        self.skip_rr_chat_ids = set(skip_rr_chat_ids)
        self.client: Optional[TelegramClient] = None
        self._running = False
        self._callback: Optional[Callable[[dict], None]] = None

    def set_on_signal(self, callback: Callable[[dict], None] | None):
        self._callback = callback

    def is_running(self) -> bool:
        return self._running

    def stop(self):
        if self.client:
            try:
                fut = asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.client.loop)
                fut.result(timeout=10)
                log.info("Client disconnected.")
            except Exception as e:
                log.error(f"Error during disconnect: {e}")
        self._running = False

    def start(self):
        if self._running:
            log.info("Bot already running.")
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)
        skip_rr_for = self.skip_rr_chat_ids

        # --- Text helper ---
        async def extract_text_from_event(ev) -> str:
            try:
                # Try caption/text/combined
                msg = getattr(ev, "message", None) or getattr(ev, "messages", [None])[0]
                if msg:
                    if getattr(msg, "message", None):
                        return msg.message or ""
                    # For albums, some items have text in first message
                # Fallback for NewMessage event
                if hasattr(ev, "raw_text"):
                    return ev.raw_text or ""
            except Exception:
                pass
            return ""

        # --- Handlers ---
        @self.client.on(events.NewMessage(chats=self.from_channels))
        async def on_new_message(event):
            await self._process_event(event, skip_rr_for)

        # Album (grouped media) – parse caption text if present
        try:
            @self.client.on(events.Album(chats=self.from_channels))
            async def on_album(event):
                await self._process_event(event, skip_rr_for)
        except Exception:
            # Some Telethon versions may not have events.Album
            pass

        self._running = True
        log.info("Starting Telegram client...")
        self.client.start()

        async def _verify():
            # Sources
            for c in self.from_channels:
                try:
                    ent = await self.client.get_entity(c)
                    title = getattr(ent, "title", str(ent))
                    cid = getattr(ent, "id", c)
                    log.info(f"Listening source: {title} (id={cid})")
                except ChannelPrivateError:
                    log.error(f"Cannot access source '{c}': ChannelPrivateError (not a participant or private).")
                except Exception as e:
                    log.error(f"Cannot access source '{c}': {e}")
            # Destination
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

    async def _process_event(self, event, skip_rr_for):
        try:
            # Extract raw text / caption
            text = ""
            try:
                if hasattr(event, "message") and event.message:
                    # NewMessage
                    text = event.message.message or ""
                elif hasattr(event, "messages") and event.messages:
                    # Album
                    candidate = event.messages[0]
                    text = getattr(candidate, "message", "") or ""
            except Exception:
                pass

            # Normalize early for logging
            ntext = normalize_text(text)
            snippet = (ntext or "")[:200].replace("\n", " ")
            log.info(f"MSG from {getattr(event, 'chat_id', 'unknown')}: {snippet} ...")

            formatted = parse_signal(text, getattr(event, "chat_id", 0), skip_rr_for)
            if formatted:
                try:
                    await self.client.send_message(self.to_channel, formatted)
                    log.info(f"SENT to {self.to_channel}")
                    if self._callback:
                        try:
                            self._callback({
                                "source_chat_id": str(getattr(event, "chat_id", "")),
                                "text": formatted
                            })
                        except Exception:
                            pass
                except (ChatWriteForbiddenError, ChatAdminRequiredError) as e:
                    log.error(f"Send failed (permissions): {e}")
                except FloodWaitError as e:
                    log.warning(f"FloodWait {e.seconds}s. Backing off...")
                    await asyncio.sleep(e.seconds + 1)
                except Exception as e:
                    log.error(f"Send failed: {e}")
            else:
                log.info("IGNORED (not classified as signal)")

        except Exception as e:
            log.error(f"Handler error: {e}")
