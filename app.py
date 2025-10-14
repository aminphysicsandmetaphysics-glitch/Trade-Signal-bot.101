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

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
import secrets
from itsdangerous import BadSignature, URLSafeTimedSerializer

from signal_bot import SignalBot, parse_signal, CHANNEL_PROFILES
from profiles import ChannelProfile, ProfileStore


# ----------------------------------------------------------------------------
# Flask app initialisation
# ----------------------------------------------------------------------------

app = Flask(__name__)

secret = os.environ.get("SESSION_SECRET")
if not secret:
    raise RuntimeError("SESSION_SECRET environment variable must be set")
app.secret_key = secret

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

csrf_serializer = URLSafeTimedSerializer(secret)


def generate_csrf_token() -> str:
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe()
    return csrf_serializer.dumps(session["_csrf_token"])


@app.before_request
def csrf_protect():
    if app.config.get("WTF_CSRF_ENABLED", True) and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
        if not token:
            return "Missing CSRF token", 400
        try:
            token_val = csrf_serializer.loads(token, max_age=3600)
        except BadSignature:
            return "Invalid CSRF token", 400
        if token_val != session.get("_csrf_token"):
            return "Invalid CSRF token", 400


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": generate_csrf_token}


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

# Profiles are persisted to disk using :class:`ProfileStore`.  Each
# profile is keyed by a unique ``name`` and stores channel lists along
# with optional parsing options.
profile_store_path = os.environ.get("PROFILE_STORE_PATH", "profiles.json")
profiles_store = ProfileStore(profile_store_path)


def _profile_to_dict(profile: ChannelProfile) -> dict:
    """Convert a :class:`ChannelProfile` into the API/templating dict."""
    return {
        "name": profile.id,
        "from_channels": profile.member_channels,
        "to_channels": profile.destinations,
        "parse_options": profile.parse_options,
        "templates": profile.templates,
    }


def _update_channel_profiles(profile: ChannelProfile) -> None:
    """Populate ``CHANNEL_PROFILES`` for the channels in *profile*."""
    opts = profile.parse_options or {}
    for ch in profile.member_channels:
        try:
            CHANNEL_PROFILES[int(ch)] = opts
        except Exception:
            continue


def _remove_channel_profiles(profile: ChannelProfile) -> None:
    """Remove channel mappings for *profile* from ``CHANNEL_PROFILES``."""
    for ch in profile.member_channels:
        try:
            CHANNEL_PROFILES.pop(int(ch), None)
        except Exception:
            continue


def _load_profiles_into_channel_profiles() -> None:
    """Load all profiles and populate ``CHANNEL_PROFILES`` accordingly."""
    CHANNEL_PROFILES.clear()
    for p in profiles_store.list_profiles().values():
        _update_channel_profiles(p)


_load_profiles_into_channel_profiles()


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
        """Authentication is disabled; simply invoke the view."""
        return func(*args, **kwargs)

    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    flash("ورود لازم نیست؛ مستقیماً از داشبورد استفاده کنید.", "info")
    return redirect(url_for("index"))


# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------

@app.route("/", methods=["GET"])
@login_required
def index():
    cfg = config_store
    return render_template("index.html", cfg=cfg)


@app.route("/profiles", methods=["GET"])
@login_required
def profiles_page():
    """Render a simple listing of available profiles."""
    profiles = {p.id: _profile_to_dict(p) for p in profiles_store.list_profiles().values()}
    return render_template("profiles.html", profiles=profiles)


@app.route("/profiles/new", methods=["GET"])
@login_required
def new_profile_page():
    """Render form for creating a new profile."""
    return render_template("profile.html", profile=None)


@app.route("/profiles/<name>", methods=["GET"])
@login_required
def edit_profile_page(name: str):
    """Render form for editing an existing profile."""
    profile = profiles_store.get_profile(name)
    if not profile:
        flash("Profile not found.", "error")
        return redirect(url_for("profiles_page"))
    return render_template("profile.html", profile=_profile_to_dict(profile))


# -----------------------------------------------------------------------------
# Profile REST API
# -----------------------------------------------------------------------------


@app.route("/api/profiles", methods=["GET", "POST"])
@login_required
def api_profiles():
    """List existing profiles or create a new one."""
    if request.method == "GET":
        profiles = [_profile_to_dict(p) for p in profiles_store.list_profiles().values()]
        return jsonify(profiles)

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    if profiles_store.get_profile(name):
        return jsonify({"error": "profile exists"}), 409

    profile = ChannelProfile(
        id=name,
        name=name,
        member_channels=data.get("from_channels", []),
        destinations=data.get("to_channels", []),
        parse_options=data.get("parse_options", {}),
        templates=data.get("templates", {}),
    )
    profiles_store.create_profile(profile)
    _update_channel_profiles(profile)
    return jsonify(_profile_to_dict(profile)), 201


@app.route("/api/profiles/<name>", methods=["GET", "PUT", "DELETE"])
@login_required
def api_profile(name: str):
    """Retrieve, update or delete a profile."""
    profile = profiles_store.get_profile(name)
    if not profile:
        return jsonify({"error": "not found"}), 404

    if request.method == "GET":
        return jsonify(_profile_to_dict(profile))

    if request.method == "DELETE":
        _remove_channel_profiles(profile)
        profiles_store.delete_profile(name)
        return "", 204

    data = request.get_json(silent=True) or {}
    _remove_channel_profiles(profile)
    updates = {
        "member_channels": data.get("from_channels", profile.member_channels),
        "destinations": data.get("to_channels", profile.destinations),
        "parse_options": data.get("parse_options", profile.parse_options),
        "templates": data.get("templates", profile.templates),
    }
    updated = profiles_store.update_profile(name, **updates)
    _update_channel_profiles(updated)
    return jsonify(_profile_to_dict(updated))


@app.route("/api/profiles/<name>/test", methods=["POST"])
@login_required
def api_profile_test(name: str):
    """Parse a sample message using the profile's settings."""
    profile = profiles_store.get_profile(name)
    if not profile:
        return jsonify({"error": "not found"}), 404

    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    # Use first from_channel as chat_id if available
    chat_id = 0
    channels = profile.member_channels or []
    if channels:
        first = channels[0]
        try:
            chat_id = int(first)
        except Exception:
            chat_id = 0

    result = parse_signal(message, chat_id, profile.parse_options)
    return jsonify({"parsed": result})


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
    if not bot_instance or not bot_instance.is_running():
        flash("Bot is not running.", "warning")
    elif not getattr(bot_instance, "loop", None) or not bot_instance.loop.is_running():
        flash("Bot loop is not running.", "warning")
    else:
        asyncio.run_coroutine_threadsafe(bot_instance.stop(), bot_instance.loop)
        flash("Bot stopped.", "success")
    return redirect(url_for("index"))


@app.route("/status")
def status():
    running = bool(bot_instance and bot_instance.is_running())
    return jsonify({"running": running})


@app.route("/dashboard")
@login_required
def dashboard():
    stats = (
        bot_instance.stats.snapshot()
        if bot_instance
        else {"received": 0, "filtered": 0, "parsed": 0, "sent": 0, "rejected": 0, "messages": []}
    )
    return render_template("dashboard.html", stats=stats)

@app.route("/health")
def health():
    return "OK", 200


if __name__ == "__main__":
    # Run the development server
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
