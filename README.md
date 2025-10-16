# Trade-Signal-Bot v2.0

Production-ready Telegram Signal Forwarder/Normalizer with:
- New 2X Club Persian parser
- Forex/Crypto templating
- R/R auto calculation (as ratio `1/N`)
- Best Entry selection for Crypto (LONG=min entry, SHORT=max entry)
- Auto-append USDT if missing
- Sends to @SuperTradersClub_bot with /signal_users before each signal
- Minimal modern Dashboard (Tailwind + Chart.js)
- Flask + Telethon (user session), suitable for Render.com

## Quick Start

1) **Environment variables (Render.com → Environment):**
```
API_ID=your_telegram_api_id
API_HASH=your_telegram_api_hash
SESSION_STRING=your_telethon_session_string
SESSION_SECRET=some_random_string
ADMIN_USER=admin
ADMIN_PASS=strongpassword
SOURCES='["@YourSource1", "@YourSource2"]'   # include 2X Club channel username/ID
DEST_BOT_USERNAME=@SuperTradersClub_bot
```
*(Optional)*
```
BOT_TOKEN_DEST=8133999742:AAE...      # only if you need Bot API elsewhere
BOT_TOKEN_OLD=7725648584:AAF...       # legacy token
```

2) **Install:**
```
pip install -r requirements.txt
```

3) **Run (dev):**
```
python run.py
# Flask on http://0.0.0.0:8000 (by default), Telethon listener starts in background.
```

4) **Gunicorn (prod):**
```
gunicorn -c gunicorn.conf.py wsgi:app
```
