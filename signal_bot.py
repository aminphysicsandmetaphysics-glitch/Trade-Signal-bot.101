from __future__ import annotations
import os
import re
import json
import asyncio
import base64
import logging
from typing import Iterable, Optional, Dict, List, Union

from telethon import TelegramClient, events
from telethon.errors import ChatWriteForbiddenError, ChatAdminRequiredError, ChannelPrivateError

log = logging.getLogger("signal-bot")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

# ---------- Parsers ----------
PAIR_RE = re.compile(r"(#?\b(?:XAUUSD|XAGUSD|GOLD|SILVER|USOIL|UKOIL|[A-Z]{3,5}[/ ]?[A-Z]{3,5}|[A-Z]{3,5}USD|USD[A-Z]{3,5})\b)")
NUM_RE = re.compile(r"(-?\d+(?:\.\d+)?)")
RR_RE = re.compile(r"(\b(?:R\s*/\s*R|Risk[- ]?Reward|Risk\s*:\s*Reward)\b[^0-9]*?(\d+(?:\.\d+)?)\s*[:/]\s*(\d+(?:\.\d+)?))", re.IGNORECASE)

POS_VARIANTS = [
    ("BUY LIMIT", "BUY LIMIT"),
    ("SELL LIMIT", "SELL LIMIT"),
    ("BUY STOP", "BUY STOP"),
    ("SELL STOP", "SELL STOP"),
    ("BUY", "BUY"),
    ("SELL", "SELL"),
]

NON_SIGNAL_HINTS = [
    "activated", "tp reached", "result so far", "screenshots", "cheers", "high-risk",
    "move sl", "put your sl", "risk free", "close", "closed", "delete", "running",
    "trade - update", "update", "guide", "watchlist", "broker", "subscription", "contact",
    "tp almost", "tp hit", "sl reached", "sl hit", "profits", "week", "friday", "poll",
]

TP_KEYS = ["tp", "take profit", "take-profit", "t/p", "t p"]
SL_KEYS = ["sl", "stop loss", "stop-loss", "s/l", "s l"]
ENTRY_KEYS = ["entry price", "entry", "e:"]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


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
            return norm.title().replace(" ", " ")
    if "BUY" in up:
        return "BUY"
    if "SELL" in up:
        return "SELL"
    return None


def extract_entry(lines: List[str]) -> Optional[str]:
    for l in lines:
        low = l.lower()
        if any(k in low for k in ENTRY_KEYS):
            m = NUM_RE.search(l)
            if m:
                return m.group(1)
    for l in lines:
        m = re.search(r"\b(BUY|SELL)(?:\s+(LIMIT|STOP))?\s+(-?\d+(?:\.\d+)?)\b", l, re.IGNORECASE)
        if m:
            return m.group(3)
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
            tps.extend([n for n in re.findall(NUM_RE, l)])
    # handle separate lines like TP1: 123
    if not tps:
        for l in lines:
            m = re.match(r"^\s*TP\d+\s*[:\-]\s*(-?\d+(?:\.\d+)?)\s*$", l, re.IGNORECASE)
            if m:
                tps.append(m.group(1))
    # limit to 4 tps
    return tps[:4]


def extract_rr(text: str) -> Optional[str]:
    m = RR_RE.search(text or "")
    if m:
        return f"{m.group(2)}/{m.group(3)}"
    return None


def looks_like_update(text: str) -> bool:
    return any(key in (text or "").lower() for key in NON_SIGNAL_HINTS)


def is_valid(sig: Dict) -> bool:
    return all([sig.get("symbol"), sig.get("position"), sig.get("entry"), sig.get("sl")]) and len(sig.get("tps", [])) >= 1


def to_unified(sig: Dict, chat_id: int, skip_rr_for: Iterable[int] = ()) -> str:
    parts = [f"📊 #{sig['symbol']}", f"📉 Position: {sig['position'].title()}"]
    rr = sig.get("rr")
    if rr and chat_id not in set(skip_rr_for):
        parts.append(f"❗️ R/R : {rr}")
    parts.append(f"\n💲 Entry Price : {sig['entry']}")
    for i, tp in enumerate(sig["tps"], 1):
        parts.append(f"✔️ TP{i} : {tp}")
    parts.append(f"\n🚫 Stop Loss : {sig['sl']}")
    return "\n".join(parts)


def parse_signal(text: str, chat_id: int, skip_rr_for: Iterable[int] = ()) -> Optional[str]:
    if looks_like_update(text):
        return None
    lines = [l.strip() for l in (text or "").splitlines() if l and l.strip()]
    symbol = guess_symbol(text) or ""
    position = guess_position(text) or ""
    entry = extract_entry(lines) or ""
    sl = extract_sl(lines) or ""
    tps = extract_tps(lines)
    rr = extract_rr(text)
    sig = {"symbol": symbol, "position": position, "entry": entry, "sl": sl, "tps": tps, "rr": rr}
    if not is_valid(sig):
        return None
    try:
        e = float(entry)
        if position.startswith("SELL") and all(float(tp) > e for tp in tps):
            return None
        if position.startswith("BUY") and all(float(tp) < e for tp in tps):
            return None
    except Exception:
        pass
    return to_unified(sig, chat_id, skip_rr_for)


# ---------- Channel helpers ----------
def _norm_peer(x: Union[int, str]) -> Union[int, str]:
    if isinstance(x, int):
        return x if x < 0 else int("-100" + str(x))
    s = (x or "").strip()
    s = re.sub(r"^https?://t\.me/", "", s, flags=re.IGNORECASE)
    s = s.lstrip("@")
    return s


# ---------- Bot ----------
class SignalBot:
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_name: str,
        from_channels: Iterable[Union[int, str]],
        to_channels: Iterable[Union[int, str]],
        skip_rr_chat_ids: Iterable[int] = (),
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_name = session_name or "signal_bot"
        self.from_channels = [_norm_peer(c) for c in from_channels]
        self.to_channels = [_norm_peer(c) for c in to_channels]
        self.skip_rr_chat_ids = set(int(x) for x in skip_rr_chat_ids or [])
        self._client: TelegramClient | None = None
        self._running = False
        self._loop = None

    def _ensure_session_file(self):
        b64 = os.environ.get("TG_SESSION_BASE64")
        if not b64:
            return
        path = f"{self.session_name}.session"
        if not os.path.exists(path):
            try:
                with open(path, "wb") as f:
                    f.write(base64.b64decode(b64))
                log.info("Session file restored from TG_SESSION_BASE64.")
            except Exception as e:
                log.error(f"Failed to restore session: {e}")

    def is_running(self) -> bool:
        return self._running

    async def _run(self):
        self._ensure_session_file()
        bot_token = os.environ.get("BOT_TOKEN")
        self._client = TelegramClient(self.session_name, int(self.api_id), self.api_hash)
        if bot_token:
            await self._client.start(bot_token=bot_token)
        else:
            await self._client.start()

        @self._client.on(events.NewMessage(chats=self.from_channels))
        async def handler(event):
            try:
                text = event.message.message or ""
                chat = await event.get_chat()
                chat_id = getattr(chat, "id", 0)
                fmt = parse_signal(text, chat_id, self.skip_rr_chat_ids)
                if not fmt:
                    return
                for dest in self.to_channels:
                    try:
                        await self._client.send_message(dest, fmt)
                    except (ChatWriteForbiddenError, ChatAdminRequiredError, ChannelPrivateError):
                        continue
                    except Exception as e:
                        log.error(f"Send error to {dest}: {e}")
            except Exception as e:
                log.error(f"Handler error: {e}")

        self._running = True
        log.info("Signal bot started.")
        await self._client.run_until_disconnected()
        self._running = False
        log.info("Signal bot stopped.")

    def start(self):
        if self._running:
            return
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._run())

    def stop(self):
        try:
            if self._client:
                self._loop.call_soon_threadsafe(self._client.disconnect)
        except Exception:
            pass