from flask import render_template, jsonify, request
from .service import try_parsers, render_signal
from .state import (
    counters,
    logs,
    by_market,
    start_ts,
    events,
    bot_state,
    add_event,
)

def setup_routes(app):
    @app.get("/")
    def index():
        return render_template("dashboard.html")

    @app.get("/api/status")
    def api_status():
        import time
        uptime = int(time.time() - start_ts)
        return jsonify({
            "uptime": uptime,
            "received": counters.get("received", 0),
            "parsed": counters.get("parsed", 0),
            "sent": counters.get("sent", 0),
            "rejected": counters.get("rejected", 0),
            "updates": counters.get("updates", 0),
            "by_market": by_market,
            "running": bot_state.get("running", False),
        })

    @app.get("/api/logs")
    def api_logs():
        return jsonify(list(logs))

    @app.get("/api/events")
    def api_events():
        return jsonify(list(events))

    @app.post("/api/bot/start")
    def api_bot_start():
        message = "ربات از قبل فعال بود."
        if not bot_state.get("running", False):
            bot_state["running"] = True
            message = "ربات با موفقیت فعال شد."
            add_event("🟢 ربات از طریق داشبورد فعال شد و در حال شنود است.", "success")
        return jsonify({"ok": True, "running": bot_state.get("running", False), "message": message})

    @app.post("/api/bot/stop")
    def api_bot_stop():
        message = "ربات از قبل متوقف شده بود."
        if bot_state.get("running", False):
            bot_state["running"] = False
            message = "ربات موقتا متوقف شد."
            add_event("🛑 ربات از طریق داشبورد متوقف شد و شنود متوقف گردید.", "warning")
        return jsonify({"ok": True, "running": bot_state.get("running", False), "message": message})

    @app.post("/api/test-signal")
    def api_test_signal():
        data = request.get_json(silent=True) or {}
        msg = (data.get("message") or "").strip()
        if not msg:
            return jsonify({"ok": False, "error": "پیام خالی است."}), 400

        parsed = try_parsers(msg)
        if not parsed:
            return jsonify({"ok": False, "error": "پیام شناسایی نشد یا قالب نادرست است."})

        formatted = render_signal(parsed, msg)
        return jsonify({
            "ok": True,
            "parsed": parsed,
            "formatted": formatted,
        })
