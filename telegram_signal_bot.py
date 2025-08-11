"""
Telegram Signal Forwarding Bot
==============================

This script uses the `Telethon` library to monitor several Telegram channels for
new trading signal messages, extract the relevant trading parameters, re‑format
them into a clean template, and forward the result to a list of destination
channels.  It is designed to run continuously on a headless server or free
hosting platform like Render or Railway.

Prerequisites
-------------

1. **Telegram API credentials:**  You must have a valid `api_id` and
   `api_hash` from Telegram.  These values can be obtained by creating an
   application at https://my.telegram.org.  The provided script reads them
   from environment variables `TG_API_ID` and `TG_API_HASH`.  Do **not** hard
   code these values in source control.

2. **First‑time login:**  On first run the script will ask for your phone
   number and a verification code sent to your Telegram account.  This is
   required because the bot acts as a user client in order to read messages
   from other channels.  Once authenticated, a session file (named
   `session`) is saved locally so subsequent runs will not require re‑login.

3. **Channel membership:**  The account used by the bot must be a member of
   the source channels you wish to monitor.  For private channels you need an
   invite link; for public channels you can join them manually.  In addition,
   the account (or a bot token if you choose to use Bot API instead) must
   have permission to post in the destination channels.

4. **Dependencies:**  This script depends on the `Telethon` package.  Add
   `telethon` to your `requirements.txt` so your deployment platform will
   install it automatically.

Usage
-----

Set the required environment variables before running the script:

```bash
export TG_API_ID=29278288
export TG_API_HASH=8baff9421321d1ef6f14b0511209fbe2
export TG_SESSION=mysession  # optional session name

# Comma‑separated list of source channel usernames or IDs
export TG_SOURCE_CHANNELS=hfjfdjjdd,GOLD EXCLUSIVE VIP,Forex.RR - Premium,Lingrid private signals

# Comma‑separated list of destination channel IDs/usernames
export TG_DEST_CHANNELS=-1467736193,-2123816390,-1286609636,@sjkalalsk

python telegram_signal_bot.py
```

When you deploy to a hosting platform, define these variables in the
environment settings of your service.  The negative numbers in the list of
destination channels indicate supergroup/channel IDs; a preceding `@` means a
public channel username.

Limitations
-----------

This script uses simple heuristics to detect whether a message is a trading
signal.  It looks for an instrument (e.g. `#XAUUSD` or `EURUSD`), a trade
direction (Buy/Sell), an entry price, at least one take profit (TP), and a
stop loss (SL).  Messages that do not contain all of these elements are
ignored.  Some non‑signal updates may still be missed or incorrectly parsed;
feel free to refine the regular expressions in `parse_signal` or the logic in
`is_signal` for your specific channels.

"""

import asyncio
import os
import re
from typing import List, Optional, Tuple

from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel



def parse_signal(message_text: str) -> Optional[Tuple[str, str, Optional[str], str, List[str], str]]:
    """Parse a trading signal from raw message text.

    Returns a tuple with the following fields on success:

        instrument (str): e.g. "XAUUSD" or "EURUSD" or "GOLD"
        position (str): e.g. "BUY", "SELL", "BUY LIMIT", etc.
        rr (Optional[str]): risk/reward ratio in the form "1/3" if available
        entry_price (str): numeric entry price
        tps (List[str]): list of take profit prices
        stop_loss (str): numeric stop loss price

    If the message cannot be parsed as a signal it returns ``None``.
    """
    # Normalize line endings and remove zero‑width characters
    text = message_text.replace('\r', '')
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    instrument: Optional[str] = None
    position: Optional[str] = None
    rr: Optional[str] = None
    entry_price: Optional[str] = None
    stop_loss: Optional[str] = None
    tps: List[str] = []

    # Regular expressions used for parsing
    rr_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*[:/]\s*(\d+(?:\.\d+)?)')
    number_pattern = re.compile(r'\d+(?:\.\d+)?')

    for i, line in enumerate(lines):
        lower_line = line.lower()

        # Instrument detection: look for hashtags first
        if not instrument:
            hash_match = re.search(r'#([a-z0-9]+)', lower_line)
            if hash_match:
                instrument = hash_match.group(1).upper()
        # If still unknown, try to parse currency pair or commodity at start of message
        if not instrument and i == 0:
            first_tokens = line.split()
            if first_tokens:
                candidate = first_tokens[0].upper()
                # Accept common lengths: 4 (e.g. GOLD), 6 (EURUSD) or 7 (BTCUSD), or 3 letters + 'USD'
                if re.fullmatch(r'[A-Z0-9]{4,7}', candidate):
                    instrument = candidate

        # Position detection: look for buy/sell with optional "limit"
        if not position:
            pos_match = re.search(r'\b(buy|sell)(?:\s+limit)?\b', lower_line)
            if pos_match:
                position = pos_match.group(0).upper()

        # Risk/reward detection
        if rr is None and 'risk' in lower_line and 'reward' in lower_line:
            rr_match = rr_pattern.search(lower_line)
            if rr_match:
                rr = f"{rr_match.group(1)}/{rr_match.group(2)}"

        # Entry price detection
        if entry_price is None and (("entry price" in lower_line) or lower_line.startswith('e:')):
            num_match = number_pattern.search(line)
            if num_match:
                entry_price = num_match.group(0)

        # Take profit detection (handles TP, TP1, Tp2, etc.)
        tp_match = re.match(r'^(✔️\s*)?tp\d*\b', lower_line)
        if tp_match:
            num_match = number_pattern.search(line)
            if num_match:
                tps.append(num_match.group(0))

        # Stop loss detection
        if stop_loss is None and ('stop loss' in lower_line or lower_line.startswith('sl')):
            num_match = number_pattern.search(line)
            if num_match:
                stop_loss = num_match.group(0)

    # Additional heuristics for "Forex.RR" style messages
    # They often use "E:" for entry, "Tp:" and "Sl:"
    if entry_price is None:
        for line in lines:
            if line.lower().startswith('e:'):
                num_match = number_pattern.search(line)
                if num_match:
                    entry_price = num_match.group(0)
            if line.lower().startswith('tp:'):
                num_match = number_pattern.search(line)
                if num_match:
                    tps.append(num_match.group(0))
            if line.lower().startswith('sl:'):
                num_match = number_pattern.search(line)
                if num_match:
                    stop_loss = num_match.group(0)
        # Risk/reward ratio may appear as "Risk‑Reward Ratio:" or similar
        if rr is None:
            for line in lines:
                if 'risk' in line.lower() and 'reward' in line.lower():
                    rr_match = rr_pattern.search(line)
                    if rr_match:
                        rr = f"{rr_match.group(1)}/{rr_match.group(2)}"

    # Lingrid style messages: first line contains instrument, type and entry
    # e.g. "EURUSD BUY 1.1581"
    if entry_price is None and len(lines) > 0:
        first_line_tokens = lines[0].split()
        if len(first_line_tokens) >= 3:
            # second token is buy/sell, third token is entry price
            if first_line_tokens[1].upper() in ('BUY', 'SELL'):
                num_match = number_pattern.search(first_line_tokens[2])
                if num_match:
                    entry_price = num_match.group(0)
                # instrument and position might not be set yet
                if not instrument:
                    instrument = first_line_tokens[0].upper()
                if not position:
                    position = first_line_tokens[1].upper()
    # Lingrid: SL and TP lines: "SL 1.14800", "TP 1.18000"
    for line in lines:
        if line.lower().startswith('sl') and stop_loss is None:
            num_match = number_pattern.search(line)
            if num_match:
                stop_loss = num_match.group(0)
        if line.lower().startswith('tp') and not tp_match:
            # Avoid adding duplicate from TP detection above
            # Accept simple TP lines
            if 'tp' in line.lower() and ':' not in line.lower():
                num_match = number_pattern.search(line)
                if num_match:
                    tps.append(num_match.group(0))

    # Some messages include multiple TP lines like "TP1 : 2643", "TP2 : 2647" which
    # have been captured above.  Remove duplicates while preserving order.
    unique_tps = []
    seen = set()
    for tp in tps:
        if tp not in seen:
            unique_tps.append(tp)
            seen.add(tp)

    # Validate that we have the minimum required fields
    if all([instrument, position, entry_price, stop_loss]) and unique_tps:
        return instrument, position, rr, entry_price, unique_tps, stop_loss
    return None


def format_signal(parsed: Tuple[str, str, Optional[str], str, List[str], str]) -> str:
    """Format the parsed signal into the final template.

    The output looks like this (TP count may vary and R/R is optional):

        📊 #XAUUSD
        📉 Position: SELL LIMIT
        ❗️ R/R : 1/4

        💲 Entry Price : 2660.5
        ✔️ TP1 : 2654.5
        ✔️ TP2 : 2648.5
        ✔️ TP3 : 2642.5
        ✔️ TP4 : 2636.5

        🚫 Stop Loss : 2666.5
    """
    instrument, position, rr, entry_price, tps, stop_loss = parsed
    # Header with instrument and position
    lines = [f"📊 #{instrument}", f"📉 Position: {position}"]
    if rr:
        lines.append(f"❗️ R/R : {rr}")
    # Blank line separating header from price levels
    lines.append("")
    # Entry price
    lines.append(f"💲 Entry Price : {entry_price}")
    # Take profits
    for idx, tp in enumerate(tps, start=1):
        lines.append(f"✔️ TP{idx} : {tp}")
    # Blank line before stop loss
    lines.append("")
    lines.append(f"🚫 Stop Loss : {stop_loss}")
    return '\n'.join(lines)


def is_signal_message(text: str) -> bool:
    """Determine if the message text contains a trading signal.

    This function first attempts to parse the message using `parse_signal`.  If
    parsing succeeds (returns a non‑None tuple), the message is considered a
    signal.  If parsing fails, or if the message contains obvious non‑signal
    keywords (e.g. "update", "close", "running", "result", etc.), it returns
    False.
    """
    lower_text = text.lower()
    # Filter out common update or informational messages
    excluded_keywords = [
        'update', 'close', 'running', 'result', 'poll', 'vote', 'risk management',
        'sale', 'promo', 'subscription', 'move sl', 'change tp', 'break even',
        'new week', 'contact', 'upgrade', 'closed', 'open trades', 'lot size'
    ]
    if any(keyword in lower_text for keyword in excluded_keywords):
        return False
    return parse_signal(text) is not None


async def main() -> None:
    """Main asynchronous entry point for the bot."""
    # Load api_hash credentials from environment variables
      api_id = os.environ.get('TG_API  _ID')
      api_hash = os.environ.get('TG_API_HASH')
    session_name = os.environ.get('TG_SESSION', 'session')
       session_b64 = os.environ.get('TG_SESSION_BASE64')
    session_file = f"{session_name}.session"
    if session_b64 and not os.path.exists(session_file):
        try:
            import base64
            decoded = base64.b64decode(session_b64)
            with open(session_file, 'wb') as f:
                f.write(decoded)
            print(f"Decoded session data written to {session_file}")
        except Exception as e:
            # Log and continue; if decoding fails the bot will prompt for login
            print(f"Failed to decode TG_SESSION_BASE64: {e}")
    if not api_id or not api_hash:
        raise RuntimeError('TG_API_ID and TG_API_HASH must be set in the environment')

    # Parse source and destination channels from environment
    raw_sources = os.environ.get('TG_SOURCE_CHANNELS', '')
    raw_destinations = os.environ.get('TG_DEST_CHANNELS', '')
    if not raw_sources or not raw_destinations:
        raise RuntimeError('TG_SOURCE_CHANNELS and TG_DEST_CHANNELS must be set')
    source_channels: List[str] = [c.strip() for c in raw_sources.split(',') if c.strip()]
    destination_channels: List[str] = [c.strip() for c in raw_destinations.split(',') if c.strip()]

    # Initialize the Telegram client
    client = TelegramClient(session_name, int(api_id), api_hash)

    @client.on(events.NewMessage(chats=source_channels))
    async def handler(event: events.NewMessage.Event) -> None:
        # Only process text messages
        if not event.message or not event.message.text:
            return
        text = event.message.text
        if not is_signal_message(text):
            return
        parsed = parse_signal(text)
        if not parsed:
            return
        formatted_message = format_signal(parsed)
        # Send the formatted message to each destination channel
        for dest in destination_channels:
            try:
                # Convert numeric strings to PeerChannel automatically
                # Telethon allows sending by username (e.g. @channelname) or ID (int)
                await client.send_message(dest, formatted_message)
            except Exception as e:
                print(f"Failed to forward to {dest}: {e}")

    # Start the client (login) and run indefinitely
    await client.start()
    print('Signal forwarding bot is now running...')
    await client.run_until_disconnected()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Bot stopped by user')
