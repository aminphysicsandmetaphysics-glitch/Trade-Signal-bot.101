"""Telegram forwarding bot for Render worker.

This script defines a resilient Telethon client that listens for new
messages in a source channel and forwards them to one or more
destination chats. It is designed to run as a long‑lived process in
background worker environments such as Render. The code includes
automatic restart logic, graceful handling of Telegram flood waits,
and minimal logging for troubleshooting.

Environment variables:
    API_ID (int): Telegram API ID from https://my.telegram.org.
    API_HASH (str): Telegram API hash from https://my.telegram.org.
    SESSION_STRING (str): StringSession for the account or bot.
    SRC (str, optional): Identifier of the source chat/channel. May be
        a numeric ID (e.g. ``-1001234567890``) or username (``@channel``).
        If omitted, the bot listens to all incoming messages.
    DST (str, optional): Comma‑separated list of destination chat
        identifiers (IDs or usernames). Messages from SRC will be
        forwarded to each destination in this list.

Usage:
    python signal_bot.py

Ensure the environment variables are set appropriately. For security
reasons, avoid committing your SESSION_STRING to version control.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Iterable, Optional, Union

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, RpcError
from telethon.sessions import StringSession

# Configure a basic logger. This will print messages to stdout when run
# under Render's logging infrastructure. The format includes the
# timestamp, log level, and the message for easy parsing.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def parse_chat_list(value: Optional[str]) -> list[Union[int, str]]:
    """Parse a comma‑separated list of chat identifiers.

    If the input is None or empty, returns an empty list. Numeric
    strings are converted to integers (to support numeric chat IDs);
    other values are left as strings.

    :param value: Comma‑separated identifiers (may be None).
    :returns: List of chat IDs as ints or usernames as strs.
    """
    if not value:
        return []
    result: list[Union[int, str]] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        # Convert numeric identifiers to int; negative numbers are valid
        if part.lstrip("-").isdigit():
            try:
                result.append(int(part))
            except ValueError:
                result.append(part)
        else:
            result.append(part)
    return result


def get_env_int(name: str) -> int:
    """Retrieve an integer environment variable or raise.

    Provides a helpful error message if the variable is missing or
    cannot be converted to an integer.

    :param name: The name of the environment variable.
    :returns: The integer value of the variable.
    :raises KeyError: If the variable is not set.
    :raises ValueError: If the value cannot be parsed as an integer.
    """
    raw = os.environ[name]
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer") from exc


def build_client() -> TelegramClient:
    """Construct a Telethon client using a session string or file.

    This helper reads ``API_ID`` and ``API_HASH`` from the environment,
    and attempts to build a client from ``SESSION_STRING`` if it is
    defined. Falling back to ``SESSION_NAME`` allows legacy `.session`
    files to be used when a string session is not provided.

    :returns: A configured ``TelegramClient`` instance ready to connect.
    """
    api_id = get_env_int("API_ID")
    api_hash = os.environ["API_HASH"]
    sess_str = os.environ.get("SESSION_STRING")
    if sess_str:
        # Use the provided string session for authentication. This avoids
        # relying on a physical .session file and allows secrets to be
        # stored in environment variables.
        session: Union[StringSession, str] = StringSession(sess_str)
    else:
        # Fall back to a named session file. Telethon will look for
        # ``<session_name>.session`` relative to the working directory.
        session_name = os.environ.get("SESSION_NAME", "signal_bot")
        session = session_name
    return TelegramClient(
        session,
        api_id,
        api_hash,
        # Override device properties for better stability with Telegram
        system_version="Windows 10",
        device_model="Render Worker",
        app_version="1.0",
        lang_code="en",
    )


async def forward_message(
    client: TelegramClient, event: events.NewMessage.Event, dests: Iterable[Union[int, str]]
) -> None:
    """Forward an incoming message to multiple destinations.

    Handles FloodWaitError by waiting and retrying. Retries up to three
    times on transient errors and skips the destination on persistent
    errors.

    :param client: The Telethon client.
    :param event: The incoming message event.
    :param dests: Iterable of destinations to forward to.
    """
    for dest in dests:
        attempt = 0
        while True:
            try:
                await client.forward_messages(dest, event.message)
                break
            except FloodWaitError as e:
                delay = int(getattr(e, "seconds", 0)) + 1
                logging.warning(
                    f"Flood wait for {delay}s when forwarding to {dest}; sleeping..."
                )
                await asyncio.sleep(delay)
            except RpcError as e:
                # Permanent error such as lack of permissions or invalid chat
                logging.error(f"RPC error forwarding to {dest}: {e!r}; skipping")
                break
            except Exception as e:
                attempt += 1
                if attempt > 3:
                    logging.exception(
                        f"Unrecoverable error forwarding to {dest}: {e!r}; giving up"
                    )
                    break
                logging.warning(
                    f"Error forwarding to {dest}: {e!r}; retrying ({attempt}/3)"
                )
                await asyncio.sleep(2 * attempt)


async def run_once() -> None:
    """Run the Telegram bot once until disconnected.

    This function starts the client, logs into Telegram and sets up the
    message handler. If the connection drops, this coroutine returns
    control to the caller (for external restart logic).
    """
    client = build_client()
    src_raw = os.environ.get("SRC", "").strip() or None
    src_chat: Optional[Union[int, str]]
    if src_raw:
        # Parse single source ID or username
        src_chat = parse_chat_list(src_raw)[0]
    else:
        src_chat = None
    dests = parse_chat_list(os.environ.get("DST"))
    await client.start()
    me = await client.get_me()
    logging.info(f"Connected to Telegram as {me.username or me.id}")
    # Define handler inside to capture current dests and src_chat
    @client.on(events.NewMessage(chats=src_chat))
    async def handler(event: events.NewMessage.Event) -> None:
        try:
            logging.info(f"Received message {event.id} from {event.chat_id}")
            if dests:
                await forward_message(client, event, dests)
            else:
                logging.warning("No destinations configured; skipping forward")
        except Exception:
            logging.exception("Unhandled error in message handler")
    # Send startup message to self if possible
    try:
        await client.send_message("me", "✅ Bot started on Render.")
    except Exception:
        # It's fine if we can't send to ourselves (e.g. bot accounts)
        pass
    # Wait indefinitely until disconnected
    await client.run_until_disconnected()


def main() -> None:
    """Main entry point with automatic restart.

    This function wraps ``run_once`` in a loop to automatically
    reconnect if the client crashes due to network issues or schema
    changes. A small delay is inserted between restarts.
    """
    while True:
        try:
            asyncio.run(run_once())
        except Exception:
            logging.exception("Bot crashed; restarting in 5 seconds")
            time.sleep(5)


if __name__ == "__main__":
    main()