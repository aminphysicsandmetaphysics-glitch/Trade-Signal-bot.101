from __future__ import annotations
import os
import json
from threading import Thread
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

from models import db, Config, Signal
from signal_bot import SignalBot

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

db_uri = os.environ.get("DATABASE_URL", "sqlite:///signal_bot.db")
app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300}
db.init_app(app)
with app.app_context():
    db.create_all()

bot: SignalBot | None = None
thread: Thread | None = None


def _json(s: str | None, default):
    try:
        return json.loads(s or "") if s else default
    except Exception:
        return default


@app.route("/", methods=["GET"])
def index():
    cfg = Config.query.first()
    if not cfg:
        cfg = Config(
            api_id=os.environ.get("TG_API_ID", ""),
            api_hash=os.environ.get("TG_API_HASH", ""),
            session_name=os.environ.get("TG_SESSION", "signal_bot"),
            from_channels=json.dumps(os.environ.get("TG_SOURCE_CHANNELS", "").split(",")) if os.environ.get("TG_SOURCE_CHANNELS") else "[]",
            to_channels=json.dumps(os.environ.get("TG_DEST_CHANNELS", "").split(",")) if os.environ.get("TG_DEST_CHANNELS") else "[]",
            skip_rr=json.dumps(os.environ.get("SKIP_RR_IDS", "1286609636").split(",")),
        )
        db.session.add(cfg)
        db.session.commit()
    running = bool(bot and bot.is_running())
    return render_template("index.html", cfg=cfg, running=running)


@app.route("/save", methods=["POST"])
def save():
    cfg = Config.query.first() or Config()
    cfg.api_id = request.form.get("api_id", "").strip()
    cfg.api_hash = request.form.get("api_hash", "").strip()
    cfg.session_name = request.form.get("session_name", "signal_bot").strip()
    cfg.from_channels = request.form.get("from_channels", "[]").strip()
    cfg.to_channels = request.form.get("to_channels", "[]").strip()
    cfg.skip_rr = request.form.get("skip_rr", "[]").strip()
    db.session.add(cfg)
    db.session.commit()
    flash("Saved.", "success")
    return redirect(url_for("index"))


@app.route("/start", methods=["POST"])
def start():
    global bot, thread
    cfg = Config.query.first()
    if bot and bot.is_running():
        flash("Already running", "warning")
        return redirect(url_for("index"))
    fc = _json(cfg.from_channels, [])
    tc = _json(cfg.to_channels, [])
    skip = [int(x) for x in _json(cfg.skip_rr, []) if str(x).strip()]
    bot = SignalBot(int(cfg.api_id), cfg.api_hash, cfg.session_name, fc, tc, skip_rr_chat_ids=skip)
    thread = Thread(target=bot.start, daemon=True)
    thread.start()
    flash("Bot started.", "success")
    return redirect(url_for("index"))


@app.route("/stop", methods=["POST"])
def stop():
    global bot
    if bot:
        bot.stop()
    flash("Bot stopped.", "success")
    return redirect(url_for("index"))


@app.route("/status")
def status():
    return jsonify({"running": bool(bot and bot.is_running())})


@app.route("/health")
def health():
    return "OK", 200