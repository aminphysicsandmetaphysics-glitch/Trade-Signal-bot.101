import os
import json
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from .service import handle_incoming_message
from .state import counters, logs, by_market, add_event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("signal-bot.worker")

def _load_sources():
    val = os.environ.get("SOURCES", "[]")
    try:
        arr = json.loads(val) if val.strip().startswith("[") else [x.strip() for x in val.split(",") if x.strip()]
        return arr
    except Exception:
        logger.exception("Failed to parse SOURCES")
        add_event("⚠️ مقادیر SOURCES قابل پردازش نبودند؛ از مقدار پیش‌فرض استفاده می‌شود.", "warning")
        return []

async def start_worker():
    api_id = int(os.environ["API_ID"])
    api_hash = os.environ["API_HASH"]
    session_string = os.environ.get("SESSION_STRING")
    session_name = os.environ.get("SESSION_NAME", "signal-bot-session")

    add_event("🚀 فرآیند راه‌اندازی کلاینت تلگرام آغاز شد.", "info")

    if session_string:
        client = TelegramClient(StringSession(session_string), api_id, api_hash)
    else:
        client = TelegramClient(session_name, api_id, api_hash)

    try:
        await client.start()
    except Exception:
        logger.exception("Failed to start Telethon client")
        add_event("❌ راه‌اندازی کلاینت تلگرام با خطا مواجه شد.", "error")
        raise

    logger.info("Telethon client started.")
    add_event("🟢 کلاینت تلگرام با موفقیت راه‌اندازی شد.", "success")

    sources = _load_sources()
    logger.info(f"SOURCES: {sources}")
    if sources:
        formatted_sources = ", ".join(str(src) for src in sources)
        add_event(
            f"👂 ربات در حال گوش دادن به منابع مشخص‌شده است: {formatted_sources}",
            "info",
        )
    else:
        add_event(
            "👂 منبع خاصی تنظیم نشده است؛ ربات به همه پیام‌های مجاز گوش می‌دهد.",
            "warning",
        )

    dest_bot = os.environ.get("DEST_BOT_USERNAME", "@SuperTradersClub_bot")
    add_event(
        f"🎯 سیگنال‌های تأییدشده به مقصد {dest_bot} ارسال خواهند شد.",
        "info",
    )

    @client.on(events.NewMessage(chats=sources if sources else None))
    async def on_new_message(event):
        try:
            text = event.raw_text or ""
            await handle_incoming_message(client, text, counters=counters, logs=logs, by_market=by_market)
        except Exception as e:
            counters["rejected"] = counters.get("rejected", 0) + 1
            logger.exception("Error handling message: %s", e)
            add_event("❌ خطا در پردازش پیام ورودی رخ داد.", "error")

    try:
        await client.run_until_disconnected()
    finally:
        add_event("🔴 ارتباط با تلگرام متوقف شد و ربات دیگر در حال شنود نیست.", "warning")
        logger.info("Telethon client stopped.")
