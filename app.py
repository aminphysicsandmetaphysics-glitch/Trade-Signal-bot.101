"""Flask dashboard for configuring and controlling the Telegram signal bot.

This application persists API credentials and channel settings in a
SQLite database via SQLAlchemy.  A simple web interface allows you to
update the configuration and start/stop the Telethon bot at runtime.

On startup, if the database contains no configuration row and
environment variables `API_ID` and `API_HASH` are set, a default
configuration will be created from `SOURCES`, `DESTS` and
`SESSION_NAME`.  This makes zero‑click deployment on Render possible.
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


# ----------------------------------------------------------------------------
# Flask app initialisation
# ----------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)


# ----------------------------------------------------------------------------
# Database configuration
# ----------------------------------------------------------------------------

db_uri = os.environ.get("DATABASE_URL", "sqlite:///signal_bot.db")
app.config["SQLALCHEMY_DATABASE_URI"] = db_uri

# Use pool_pre_ping to recycle dead connections and check_same_thread=False
# so that the Flask app and Telethon can share the same SQLite file.
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "connect_args": {"check_same_thread": False},
}

db.init_app(app)


# ----------------------------------------------------------------------------
# Global bot instance
# ----------------------------------------------------------------------------

bot_instance: SignalBot | None = None


# ----------------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------------

def parse_from_channels(raw: str | None) -> list:
    """Deserialize a JSON array of source channel identifiers.

    Accepts either a JSON-encoded list or a comma/space separated string.
    Returns an empty list on error.
    """
    if not raw:
        return []
    raw = raw.strip()
    # Try JSON first
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    # Fallback: split by commas
    parts = [p.strip() for p in re.split(r"[,\s]+", raw) if p.strip()]
    return parts


def ensure_default_config():
    """Create a default configuration row if none exists and environment vars are set."""
    with app.app_context():
        cfg = Config.query.first()
        if cfg:
            return
        # Pull from environment
        api_id = os.environ.get("API_ID")
        api_hash = os.environ.get("API_HASH")
        sources_env = os.environ.get("SOURCES")
        dests_env = os.environ.get("DESTS")
        session_name = os.environ.get("SESSION_NAME", "signal_bot")
        if api_id and api_hash and dests_env:
            try:
                sources = json.loads(sources_env) if sources_env else []
                dests = json.loads(dests_env)
                to_channel = dests[0] if dests else None
            except Exception:
                sources = []
                to_channel = None
            cfg = Config(
                api_id=api_id,
                api_hash=api_hash,
                session_name=session_name,
                from_channels=json.dumps(sources),
                to_channel=to_channel,
            )
            db.session.add(cfg)
            db.session.commit()


# Create tables and ensure default config on startup
with app.app_context():
    db.create_all()
    ensure_default_config()


def on_signal_saved(payload: dict) -> None:
    """Optional callback to persist a minimal record of forwarded signals."""
    try:
        s = Signal(
            symbol="",
            position="",
            entry="",
            sl="",
            rr=None,
            tps=json.dumps([]),
            source_chat_id=payload.get("source_chat_id"),
        )
        db.session.add(s)
        db.session.commit()
    except Exception as e:
        app.logger.error(f"Save signal error: {e}")


# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    cfg = Config.query.first()
    return render_template("index.html", cfg=cfg)


@app.route("/save_config", methods=["POST"])
def save_config():
    api_id = request.form.get("api_id", "").strip()
    api_hash = request.form.get("api_hash", "").strip()
    session_name = request.form.get("session_name", "signal_bot").strip()
    from_channels = request.form.get("from_channels", "").strip()
    to_channel = request.form.get("to_channel", "").strip()

    cfg = Config.query.first()
    if not cfg:
        cfg = Config()
        db.session.add(cfg)

    cfg.api_id = api_id
    cfg.api_hash = api_hash
    cfg.session_name = session_name
    cfg.from_channels = from_channels
    cfg.to_channel = to_channel
    db.session.commit()
    flash("Saved configuration.", "success")
    return redirect(url_for("index"))


@app.route("/start_bot", methods=["POST"])
def start_bot():
    global bot_instance
    cfg = Config.query.first()
    if not cfg or not cfg.api_id or not cfg.api_hash or not cfg.to_channel:
        flash("Please fill API ID, API HASH and destination channel.", "error")
        return redirect(url_for("index"))
    if bot_instance and bot_instance.is_running():
        flash("Bot is already running.", "warning")
        return redirect(url_for("index"))

    # Parse sources
    from_channels = parse_from_channels(cfg.from_channels)
    # Channels that should not display R/R values
    skip_rr: set[int] = set()

    bot_instance = SignalBot(
        api_id=int(cfg.api_id),
        api_hash=cfg.api_hash,
        session_name=cfg.session_name or "signal_bot",
        from_channels=from_channels,
        to_channel=cfg.to_channel,
        skip_rr_chat_ids=skip_rr,
    )
    # Optionally persist a minimal history
    bot_instance.set_on_signal(on_signal_saved)
    t = Thread(target=bot_instance.start, daemon=True)
    t.start()
    flash("Bot started.", "success")
    return redirect(url_for("index"))


@app.route("/stop_bot", methods=["POST"])
def stop_bot():
    global bot_instance
    if bot_instance and bot_instance.is_running():
        bot_instance.stop()
        flash("Bot stopped.", "success")
    else:
        flash("Bot is not running.", "warning")
    return redirect(url_for("index"))


@app.route("/status")
def status():
    running = bool(bot_instance and bot_instance.is_running())
    return jsonify({"running": running})


@app.route("/health")
def health():
    return "OK", 200


if __name__ == "__main__":
    # Run the development server
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)