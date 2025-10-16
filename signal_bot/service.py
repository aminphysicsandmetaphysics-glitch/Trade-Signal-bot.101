import asyncio
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape
from .parsers.parse_signal_2xclub import parse_signal_2xclub
from .parsers.parse_signal_generic import parse_signal_generic
from .utils.normalize import is_crypto, ensure_usdt
from .utils.rr import format_rr
from .state import (
    add_event,
    add_log_entry,
    increment_counter,
    increment_market_counter,
    is_bot_running,
)

logger = logging.getLogger("signal-bot.service")

env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape()
)

DEST_BOT = None

async def send_to_destination(client, formatted_signal: str, symbol: str | None = None):
    import os
    global DEST_BOT
    if DEST_BOT is None:
        DEST_BOT = os.environ.get("DEST_BOT_USERNAME", "@SuperTradersClub_bot")
    try:
        add_event(f"🚀 ارسال فرمان /signal_users به مقصد {DEST_BOT} آغاز شد.", "info")
        await client.send_message(DEST_BOT, "/signal_users")
        add_event(
            f"🛰️ فرمان /signal_users با موفقیت به {DEST_BOT} ارسال شد.",
            "success",
        )
        await asyncio.sleep(1.2)
        add_event(
            f"📨 سیگنال به مقصد {DEST_BOT} ارسال می‌شود: {symbol or 'نامشخص'}",
            "info",
        )
        await client.send_message(DEST_BOT, formatted_signal)
        add_event(
            f"✅ سیگنال برای {symbol or 'نامشخص'} به مقصد {DEST_BOT} ارسال شد.",
            "success",
        )
    except Exception as e:
        logger.exception(f"Failed to send to {DEST_BOT}: {e}")
        add_event(
            f"❌ ارسال پیام به مقصد {DEST_BOT} با خطا مواجه شد.",
            "error",
        )

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
    for parser in (parse_signal_2xclub, parse_signal_generic):
        parsed = parser(message_text)
        if parsed:
            return parsed
    return None

async def handle_incoming_message(client, event_text: str) -> None:
    increment_counter("received")
    add_event("📥 پیام جدیدی از کانال مبدا دریافت شد.")

    if not is_bot_running():
        add_event("⏸️ پیام دریافتی نادیده گرفته شد زیرا ربات در حالت توقف است.", "warning")
        add_log_entry(
            symbol=None,
            market=None,
            side=None,
            rr=None,
            sent=False,
        )
        return

    parsed = try_parsers(event_text)
    if not parsed:
        increment_counter("rejected")
        add_event("❌ پیام دریافتی به عنوان سیگنال شناخته نشد و رد شد.", "warning")
        return

    if parsed.get("is_update"):
        increment_counter("updates")
        add_event("ℹ️ پیام دریافتی از نوع آپدیت بود و پردازش نشد.", "info")
        return

    increment_counter("parsed")
    add_event(
        f"✅ پیام دریافتی به عنوان سیگنال پذیرفته شد: {parsed.get('symbol') or parsed.get('market_type') or 'نامشخص'}",
        "success",
    )

    if not parsed.get("rr"):
        entry, stop, targets, side = parsed.get("entry"), parsed.get("stop"), parsed.get("targets"), parsed.get("side")
        if entry and stop and targets:
            parsed["rr"] = format_rr(entry, stop, targets[0], side)

    if (parsed.get("market_type") == "Crypto") and parsed.get("symbol"):
        parsed["symbol"] = ensure_usdt(parsed["symbol"])

    formatted = render_signal(parsed, event_text)
    await send_to_destination(client, formatted, parsed.get("symbol"))

    increment_counter("sent")
    add_event(f"📤 سیگنال آماده و برای ارسال نهایی ثبت شد: {parsed.get('symbol') or '-'}", "success")
    add_log_entry(
        symbol=parsed.get("symbol"),
        market=parsed.get("market_type")
        or ("Crypto" if "USDT" in (parsed.get("symbol") or "") else "Forex"),
        side=parsed.get("side"),
        rr=parsed.get("rr"),
        sent=True,
    )
    key = (parsed.get("market_type") or "Forex").lower()
    increment_market_counter(key)
