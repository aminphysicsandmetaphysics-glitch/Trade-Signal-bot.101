# app.py
# -*- coding: utf-8 -*-

"""
Flask dashboard for configuring and controlling the Telegram signal bot.

- Persists config to SQLite via SQLAlchemy (see models.py).
- Works with the new SignalBot that reads config from environment variables.
- Supports multiple destination channels (comma-separated or JSON list).
- Removes usage of deprecated methods/params (e.g., is_running(), ctor args).

Routes:
- GET  /            -> dashboard
- POST /save        -> save config
- POST /start_bot   -> start Telethon bot (threaded)
- POST /stop_bot    -> stop/disconnect bot
- GET  /status      -> {"running": bool}
- GET  /health      -> "OK"
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from threading import Thread

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from werkzeug.middleware.proxy_fix import ProxyFix

from models import db, Config, Signal
from signal_bot import SignalBot


# ------------------------------------------------------------------------------
# Flask app initialisation
# ------------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret")
app.wsgi_app = ProxyFix(app.wsgi_app)  # type: ignore

# DB config (works on Render + local)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///signals.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

with app.app_context():
    db.create_all()

# Global bot handle (thread-safe enough for this simple dashboard)
bot_instance: SignalBot | None = None


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def _as_list(value: str | None) -> list[str]:
    """Accept JSON list or comma-separated string; return trimmed list[str]."""
    if not value:
        return []
    value = value.strip()
    if not value:
        return []
    # JSON first
    try:
        data = json.loads(value)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        pass
    # Fallback: comma separated
    return [part.strip() for part in value.split(",") if part.strip()]


def ensure_default_config() -> None:
    """
    If DB lacks a row, seed from env:
    API_ID, API_HASH, SESSION_NAME, SOURCES, DESTS
    """
    with app.app_context():
        row = Config.query.first()
        if row:
            return

        api_id = os.environ.get("API_ID")
        api_hash = os.environ.get("API_HASH")
        session_name = os.environ.get("SESSION_NAME", "signal_bot")
        sources_env = os.environ.get("SOURCES", "")
        dests_env = os.environ.get("DESTS", "")

        # We store raw strings in DB so the UI can keep user's input format.
        from_channels = sources_env.strip()
        to_channel = dests_env.strip()

        row = Config(
            api_id=int(api_id) if api_id and api_id.isdigit() else None,
            api_hash=api_hash or "",
            session_name=session_name,
            from_channels=from_channels,
            to_channel=to_channel,  # <-- keep full multi-dest, not just first item
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.session.add(row)
        db.session.commit()


def save_config_from_form() -> None:
    """Save config from request.form (keeps raw strings for channels fields)."""
    api_id_raw = (request.form.get("api_id") or "").strip()
    api_id = int(api_id_raw) if api_id_raw.isdigit() else None
    api_hash = (request.form.get("api_hash") or "").strip()
    session_name = (request.form.get("session_name") or "signal_bot").strip()
    from_channels = (request.form.get("from_channels") or "").strip()
    to_channel = (request.form.get("to_channel") or "").strip()

    with app.app_context():
        cfg = Config.query.first()
        if not cfg:
            cfg = Config(created_at=datetime.utcnow())
            db.session.add(cfg)

        cfg.api_id = api_id
        cfg.api_hash = api_hash
        cfg.session_name = session_name
        cfg.from_channels = from_channels
        cfg.to_channel = to_channel
        cfg.updated_at = datetime.utcnow()

        db.session.commit()


# Optional: persist incoming signals to DB when bot sees them
def on_signal_saved(signal_dict: dict) -> None:
    try:
        with app.app_context():
            s = Signal(
                message_id=str(signal_dict.get("message_id", "")),
                from_chat=str(signal_dict.get("from_chat", "")),
                to_chats=json.dumps(signal_dict.get("to_chats", []), ensure_ascii=False),
                text=signal_dict.get("text", ""),
                created_at=datetime.utcnow(),
            )
            db.session.add(s)
            db.session.commit()
    except Exception as e:
        app.logger.exception("Failed to save signal: %s", e)


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    ensure_default_config()
    cfg = Config.query.first()
    return render_template("index.html", cfg=cfg)


@app.route("/save", methods=["POST"])
def on_save():
    save_config_from_form()
    flash("Saved configuration.", "success")
    return redirect(url_for("index"))


@app.route("/start_bot", methods=["POST"])
def start_bot():
    global bot_instance

    cfg = Config.query.first()
    if not cfg or not cfg.api_id or not cfg.api_hash or not cfg.to_channel:
        flash("Please fill API ID, API HASH and destination channel.", "error")
        return redirect(url_for("index"))

    # Already running?
    if bot_instance:
        flash("Bot is already running.", "warning")
        return redirect(url_for("index"))

    # Parse sources/dests from DB (support JSON or comma)
    sources_list = _as_list(cfg.from_channels)
    dests_list = _as_list(cfg.to_channel)

    # Set environment for SignalBot (it reads from env)
    os.environ["API_ID"] = str(cfg.api_id)
    os.environ["API_HASH"] = cfg.api_hash
    os.environ["SESSION_NAME"] = cfg.session_name or "signal_bot"
    os.environ["SOURCES"] = json.dumps(sources_list, ensure_ascii=False)
    os.environ["DESTS"] = json.dumps(dests_list, ensure_ascii=False)

    # Create instance (no ctor args in new class)
    bot_instance = SignalBot()
    bot_instance.set_on_signal(on_signal_saved)

    # Run the bot in a background thread, driving its asyncio loop
    def run_bot():
        try:
            # SignalBot.start() is async; use its internal loop
            bot_instance.client.loop.run_until_complete(bot_instance.start())
        except Exception as e:
            app.logger.exception("Bot crashed: %s", e)
        finally:
            # ensure we reflect stopped state if it exits
            nonlocal bot_instance
            bot_instance = None

    t = Thread(target=run_bot, daemon=True)
    t.start()

    flash("Bot started.", "success")
    return redirect(url_for("index"))


@app.route("/stop_bot", methods=["POST"])
def stop_bot():
    global bot_instance

    if not bot_instance:
        flash("Bot is not running.", "warning")
        return redirect(url_for("index"))

    try:
        # Gracefully disconnect Telethon client
        bot_instance.client.loop.run_until_complete(bot_instance.client.disconnect())
    except Exception as e:
        app.logger.warning("Stop error (ignored): %s", e)
    finally:
        bot_instance = None

    flash("Bot stopped.", "success")
    return redirect(url_for("index"))


@app.route("/status", methods=["GET"])
def status():
    running = bool(bot_instance)
    return jsonify({"running": running})


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


# ------------------------------------------------------------------------------
# App startup
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    ensure_default_config()
    # Local dev server (Render will run via gunicorn)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)
