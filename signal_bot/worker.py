import os
import json
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from .service import handle_incoming_message
from .state import counters, logs, by_market

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("signal-bot.worker")

def _load_sources():
    val = os.environ.get("SOURCES", "[]")
    try:
        arr = json.loads(val) if val.strip().startswith("[") else [x.strip() for x in val.split(",") if x.strip()]
        return arr
    except Exception:
        logger.exception("Failed to parse SOURCES")
        return []

async def start_worker():
    api_id = int(os.environ["API_ID"])
    api_hash = os.environ["API_HASH"]
    session_string = os.environ.get("SESSION_STRING")
    session_name = os.environ.get("SESSION_NAME", "signal-bot-session")

    if session_string:
        client = TelegramClient(StringSession(session_string), api_id, api_hash)
    else:
        client = TelegramClient(session_name, api_id, api_hash)

    await client.start()
    logger.info("Telethon client started.")

    sources = _load_sources()
    logger.info(f"SOURCES: {sources}")

    @client.on(events.NewMessage(chats=sources if sources else None))
    async def on_new_message(event):
        try:
            text = event.raw_text or ""
            await handle_incoming_message(client, text, counters=counters, logs=logs, by_market=by_market)
        except Exception as e:
            counters["rejected"] = counters.get("rejected", 0) + 1
            logger.exception("Error handling message: %s", e)

    await client.run_until_disconnected()
