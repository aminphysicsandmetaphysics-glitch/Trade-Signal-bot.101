# app.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json, os, asyncio
from threading import Thread
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from models import db, Config, Signal
from signal_bot import SignalBot

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret")
app.wsgi_app = ProxyFix(app.wsgi_app)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///signals.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

with app.app_context():
    try:
        db.init_app(app)
    except Exception:
        pass
    db.create_all()

# single running instance
bot_instance: SignalBot | None = None

# ---------- helpers ----------
def _as_list(value: str | None) -> list[str]:
    if not value:
        return []
    value = value.strip()
    if not value:
        return []
    try:
        v = json.loads(value)
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
    except Exception:
        pass
    return [p.strip() for p in value.split(",") if p.strip()]

def ensure_default_config() -> None:
    with app.app_context():
        row = Config.query.first()
        if row:
            return
        api_id_env = os.environ.get("API_ID")
        api_hash_env = os.environ.get("API_HASH")
        session_name_env = os.environ.get("SESSION_NAME", "signal_bot")
        sources_env = os.environ.get("SOURCES", "")
        dests_env = os.environ.get("DESTS", "")
        row = Config(
            api_id=int(api_id_env) if (api_id_env and api_id_env.isdigit()) else None,
            api_hash=api_hash_env or "",
            session_name=session_name_env,
            from_channels=sources_env.strip(),
            to_channel=dests_env.strip(),
        )
        db.session.add(row)
        db.session.commit()

def save_config_from_form() -> None:
    api_id_raw = (request.form.get("api_id") or "").strip()
    api_id = int(api_id_raw) if api_id_raw.isdigit() else None
    api_hash = (request.form.get("api_hash") or "").strip()
    session_name = (request.form.get("session_name") or "signal_bot").strip()
    from_channels = (request.form.get("from_channels") or "").strip()
    to_channel = (request.form.get("to_channel") or "").strip()

    with app.app_context():
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

def on_signal_saved(signal_dict: dict) -> None:
    try:
        with app.app_context():
            s = Signal(
                message_id=str(signal_dict.get("message_id", "")),
                from_chat=str(signal_dict.get("from_chat", "")),
                to_chats=json.dumps(signal_dict.get("to_chats", []), ensure_ascii=False),
                text=signal_dict.get("text", ""),
            )
            db.session.add(s)
            db.session.commit()
    except Exception:
        # اگر مدل Signal ستون‌های فوق را نداشت، از کرش جلوگیری می‌کنیم.
        pass

# ---------- routes ----------
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

    if bot_instance:
        flash("Bot is already running.", "warning")
        return redirect(url_for("index"))

    sources_list = _as_list(cfg.from_channels)
    dests_list   = _as_list(cfg.to_channel)

    # SignalBot از ENV می‌خوانَد
    os.environ["API_ID"] = str(cfg.api_id)
    os.environ["API_HASH"] = cfg.api_hash
    os.environ["SESSION_NAME"] = cfg.session_name or "signal_bot"
    os.environ["SOURCES"] = json.dumps(sources_list, ensure_ascii=False)
    os.environ["DESTS"]   = json.dumps(dests_list,   ensure_ascii=False)

    bot_instance = SignalBot()
    if hasattr(bot_instance, "set_on_signal"):
        bot_instance.set_on_signal(on_signal_saved)

    def run_bot():
        global bot_instance
        # ✅ ایجاد و ثبت event loop مخصوص این نخ
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # ذخیرهٔ loop روی شیء برای توقف تمیز از نخ اصلی
        setattr(bot_instance, "_loop", loop)
        try:
            # اگر start خودش تا disconnect بلاک می‌کند، همین کافی است؛
            # اگر نه، run_until_disconnected حلقه را زنده نگه می‌دارد.
            loop.run_until_complete(bot_instance.start())
            if hasattr(bot_instance, "client"):
                loop.run_until_complete(bot_instance.client.run_until_disconnected())
        except Exception as e:
            app.logger.exception("Bot crashed: %s", e)
        finally:
            try:
                if not loop.is_closed():
                    loop.call_soon_threadsafe(loop.stop)
                    loop.close()
            except Exception:
                pass
            bot_instance = None

    Thread(target=run_bot, daemon=True).start()
    flash("Bot started.", "success")
    return redirect(url_for("index"))

@app.route("/stop_bot", methods=["POST"])
def stop_bot():
    global bot_instance
    if not bot_instance:
        flash("Bot is not running.", "warning")
        return redirect(url_for("index"))

    loop = getattr(bot_instance, "_loop", None)
    try:
        if loop and hasattr(bot_instance, "client"):
            # ✅ توقف امن از نخ اصلی
            fut = asyncio.run_coroutine_threadsafe(bot_instance.client.disconnect(), loop)
            try:
                fut.result(timeout=10)
            except Exception:
                pass
        else:
            # راه‌حل پشتیبان: اگر loop در دسترس نبود
            try:
                asyncio.run(bot_instance.client.disconnect())
            except Exception:
                pass
    except Exception as e:
        app.logger.warning("Stop error (ignored): %s", e)
    finally:
        bot_instance = None

    flash("Bot stopped.", "success")
    return redirect(url_for("index"))

@app.route("/status", methods=["GET"])
def status():
    return jsonify({"running": bool(bot_instance)})

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

if __name__ == "__main__":
    ensure_default_config()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)
