# Trade Signal Bot — Render-ready Deployment

This repository contains a Telegram signal‑forwarding bot designed to run 24/7 on [Render](https://render.com) using Telethon and Flask.

## Features

* Forward messages from one or more **source channels** to multiple **destination channels**.
* Intelligent signal parsing with support for multiple formats. Noise messages (updates, screenshots, etc.) are ignored.
* Compact, unified output format that omits the original source.
* Web dashboard for configuring API credentials, source/destination channels and for starting/stopping the bot.
* Automatic reconnection to Telegram if the client disconnects.

## Repository Layout

```
app.py               # Flask application with dashboard and bot lifecycle controls
signal_bot.py        # Telethon wrapper with intelligent signal parsing
gunicorn.conf.py     # Gunicorn configuration (single worker/thread)
wsgi.py              # Entrypoint for Gunicorn
requirements.txt     # Python dependencies
templates/           # HTML templates for the web dashboard
README.md            # This file
```

## Running Locally

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Generate a Telethon **session string** and keep it somewhere safe. You can obtain it with a short script:

   ```python
   from telethon.sync import TelegramClient
   from telethon.sessions import StringSession

   api_id = int(os.getenv("API_ID"))
   api_hash = os.getenv("API_HASH")

   with TelegramClient(StringSession(), api_id, api_hash) as client:
       print(client.session.save())
   ```

   Store the resulting string in an environment variable named `SESSION_STRING` or enter it in the web dashboard. **Do not commit it to git.**
3. Start the application:

   ```bash
   python app.py
   ```

4. Open http://127.0.0.1:5000 in your browser and fill in your API ID, API hash, session string, source channels and destination channels. Optionally provide channel IDs in **skip_rr_channels** to suppress R/R values for those chats. Click **Start Bot** to begin forwarding.

## Deploying to Render

1. Push this repository (without your session string) to GitHub.
2. Create a new **Web Service** on Render and point it at your repository.
3. Use the following commands when prompted:

   * **Build command**: `pip install -r requirements.txt`
   * **Start command**: `gunicorn -c gunicorn.conf.py wsgi:app`

4. In the Render dashboard, create environment variables for your bot:

   * `API_ID` – your Telegram API ID.
   * `API_HASH` – your Telegram API hash.
   * `SOURCES` – a JSON array of source channel usernames or numeric IDs (e.g. `["@sourceA", -1001234567890]`).
   * `DESTS` – a JSON array of destination channel usernames or numeric IDs.
   * `SKIP_RR_CHANNELS` – optional JSON array or comma-separated list of channel IDs for which risk/reward should be omitted.
   * `SESSION_STRING` – the session string generated earlier.

5. Deploy the service.  Once running, visit `/` to configure the bot if you have not set environment variables.  The dashboard allows you to start and stop the bot without redeploying.

## Notes

* Channel identifiers prefixed with `@` are resolved automatically.  Numeric channel IDs (e.g. 1467736193) are coerced to the proper negative format (`-1001467736193`) for Telegram API compatibility.
* If a source channel has forwarding restrictions enabled, the bot will attempt to copy the content instead of forwarding.  This fallback works for both text messages and media messages.
