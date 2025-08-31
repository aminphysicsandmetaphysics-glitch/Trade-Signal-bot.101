"""Flask dashboard for configuring and controlling the Telegram signal bot.

This application stores API credentials and channel settings in memory,
optionally initialised from environment variables.  A simple web
interface allows you to update the configuration and start/stop the
Telethon bot at runtime.
"""

from __future__ import annotations

import json
import os
import re
import asyncio
from threading import Thread
from functools import wraps

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    current_app,
)
from werkzeug.middleware.proxy_fix import ProxyFix

from signal_bot import SignalBot


# ----------------------------------------------------------------------------
# Flask app initialisation
# ----------------------------------------------------------------------------

app = Flask(__name__)

secret = os.environ.get("SESSION_SECRET")
if not secret:
    raise RuntimeError("SESSION_SECRET environment variable must be set")
app.secret_key = secret

admin_user = os.environ.get("ADMIN_USER")
admin_pass = os.environ.get("ADMIN_PASS")
if not admin_user or not admin_pass:
    raise RuntimeError("ADMIN_USER and ADMIN_PASS must be set")

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)


# ----------------------------------------------------------------------------
# In-memory configuration
# ----------------------------------------------------------------------------

config_store = {
    "api_id": os.environ.get("API_ID", ""),
    "api_hash": os.environ.get("API_HASH", ""),
    "session_string": os.environ.get("SESSION_STRING", ""),
    "from_channels": os.environ.get("SOURCES", ""),
    "to_channels": os.environ.get("DESTS", ""),
}


# ----------------------------------------------------------------------------
# Global bot instance
# ----------------------------------------------------------------------------

bot_instance: SignalBot | None = None


# ----------------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------------

def _parse_channels(raw: str | None) -> list:
    """Deserialize a JSON array or comma/space separated list of channels.

    Any element that looks like an integer (allowing a leading ``-``) will be
    converted to :class:`int` while other elements remain as strings.  This
    mirrors how Telegram channel identifiers may be provided as numeric IDs or
    usernames.
    """

    if not raw:
        return []

    raw = raw.strip()

    def _coerce(part):
        """Convert numeric strings to integers."""
        if isinstance(part, str) and re.fullmatch(r"-?\d+", part):
            try:
                return int(part)
            except ValueError:
                return part
        return part

    parts: list
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            parts = data
        else:
            raise ValueError
    except Exception:
        parts = [p.strip() for p in re.split(r"[,\s]+", raw) if p.strip()]

    return [_coerce(p) for p in parts]


def parse_from_channels(raw: str | None) -> list:
    return _parse_channels(raw)


def parse_to_channels(raw: str | None) -> list:
    return _parse_channels(raw)


# ----------------------------------------------------------------------------
# Authentication
# ----------------------------------------------------------------------------


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        disabled = {
            e.strip()
            for e in os.environ.get("DISABLE_AUTH", "").split(",")
            if e.strip()
        }
        if (
            not session.get("logged_in")
            and not current_app.config.get("TESTING")
            and request.endpoint not in disabled
        ):
            return redirect(url_for("login"))
        return func(*args, **kwargs)

    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == admin_user and password == admin_pass:
            session["logged_in"] = True
            flash("Logged in.", "success")
            return redirect(url_for("index"))
        flash("Invalid credentials.", "error")
    return render_template("login.html")


# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------

@app.route("/", methods=["GET"])
@login_required
def index():
    cfg = config_store
    return render_template("index.html", cfg=cfg)


@app.route("/save_config", methods=["POST"])
@login_required
def save_config():
    api_id = request.form.get("api_id", "").strip()
    api_hash = request.form.get("api_hash", "").strip()
    session_string = request.form.get("session_string", "").strip()
    from_channels = request.form.get("from_channels", "").strip()
    to_channels = request.form.get("to_channels", "").strip()

    config_store.update(
        {
            "api_id": api_id,
            "api_hash": api_hash,
            "session_string": session_string,
            "from_channels": from_channels,
            "to_channels": to_channels,
        }
    )
    flash("Saved configuration.", "success")
    return redirect(url_for("index"))


@app.route("/start_bot", methods=["POST"])
@login_required
def start_bot():
    global bot_instance
    cfg = config_store
    if not cfg.get("api_id") or not cfg.get("api_hash") or not cfg.get("to_channels"):
        flash("Please fill API ID, API HASH and destination channels.", "error")
        return redirect(url_for("index"))
    if bot_instance and bot_instance.is_running():
        flash("Bot is already running.", "warning")
        return redirect(url_for("index"))

    if not cfg.get("session_string"):
        flash("Please provide session string.", "error")
        return redirect(url_for("index"))

    # Parse sources and destinations
    try:
        api_id_int = int(cfg.get("api_id"))
    except (TypeError, ValueError):
        flash("API ID must be an integer.", "error")
        return render_template("index.html", cfg=cfg), 400

    from_channels = parse_from_channels(cfg.get("from_channels"))
    to_channels = parse_to_channels(cfg.get("to_channels"))

    bot_instance = SignalBot(
        api_id=api_id_int,
        api_hash=cfg.get("api_hash"),
        session_string=cfg.get("session_string") or "",
        from_channels=from_channels,
        to_channels=to_channels,
    )
    t = Thread(target=bot_instance.start, daemon=True)
    t.start()
    flash("Bot started.", "success")
    return redirect(url_for("index"))


@app.route("/stop_bot", methods=["POST"])
@login_required
def stop_bot():
    global bot_instance
    if bot_instance and bot_instance.is_running():
        asyncio.run_coroutine_threadsafe(bot_instance.stop(), bot_instance.loop)
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
