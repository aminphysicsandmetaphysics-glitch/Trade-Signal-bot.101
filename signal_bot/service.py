import asyncio
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape
from .parsers.parse_signal_2xclub import parse_signal_2xclub
from .utils.normalize import is_crypto, is_gold, ensure_usdt
from .utils.rr import format_rr

logger = logging.getLogger("signal-bot.service")

env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape()
)

DEST_BOT = None

async def send_to_destination(client, formatted_signal: str):
    import os
    global DEST_BOT
    if DEST_BOT is None:
        DEST_BOT = os.environ.get("DEST_BOT_USERNAME", "@SuperTradersClub_bot")
    try:
        await client.send_message(DEST_BOT, "/signal_users")
        await asyncio.sleep(1.2)
        await client.send_message(DEST_BOT, formatted_signal)
    except Exception as e:
        logger.exception(f"Failed to send to {DEST_BOT}: {e}")

def choose_template(parsed: dict, original_text: str) -> str:
    symbol = parsed.get("symbol") or ""
    if parsed.get("market_type") == "Crypto" or is_crypto(symbol, original_text):
        return "signal_crypto.j2"
    return "signal_forex.j2"

def render_signal(parsed: dict, original_text: str) -> str:
    tpl_name = choose_template(parsed, original_text)
    tpl = env.get_template(tpl_name)
    return tpl.render(
        symbol=parsed.get("symbol"),
        side=parsed.get("side", "LONG"),
        entry=parsed.get("entry"),
        targets=parsed.get("targets", []),
        stop=parsed.get("stop"),
        rr=parsed.get("rr"),
        leverage=parsed.get("leverage"),
    )

def try_parsers(message_text: str) -> dict | None:
    p = parse_signal_2xclub(message_text)
    if p:
        return p
    return None

async def handle_incoming_message(client, event_text: str, counters=None, logs=None, by_market=None):
    if counters is not None:
        counters["received"] = counters.get("received", 0) + 1

    parsed = try_parsers(event_text)
    if not parsed:
        if counters is not None:
            counters["rejected"] = counters.get("rejected", 0) + 1
        return

    if parsed.get("is_update"):
        if counters is not None:
            counters["updates"] = counters.get("updates", 0) + 1
        return

    if counters is not None:
        counters["parsed"] = counters.get("parsed", 0) + 1

    if not parsed.get("rr"):
        entry, stop, targets, side = parsed.get("entry"), parsed.get("stop"), parsed.get("targets"), parsed.get("side")
        if entry and stop and targets:
            parsed["rr"] = format_rr(entry, stop, targets[0], side)

    if (parsed.get("market_type") == "Crypto") and parsed.get("symbol"):
        parsed["symbol"] = ensure_usdt(parsed["symbol"])

    formatted = render_signal(parsed, event_text)
    await send_to_destination(client, formatted)

    if counters is not None:
        counters["sent"] = counters.get("sent", 0) + 1
    if logs is not None:
        logs.append({
            "ts": None,
            "symbol": parsed.get("symbol"),
            "market": parsed.get("market_type") or ("Crypto" if "USDT" in (parsed.get("symbol") or "") else "Forex"),
            "side": parsed.get("side"),
            "rr": parsed.get("rr"),
            "sent": True,
        })
    if by_market is not None:
        key = (parsed.get("market_type") or "Forex").lower()
        by_market[key] = by_market.get(key, 0) + 1
