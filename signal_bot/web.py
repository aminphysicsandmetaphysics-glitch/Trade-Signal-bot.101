from flask import render_template, jsonify, request
from .service import try_parsers, render_signal
from .state import (
    add_event,
    get_by_market,
    get_counters,
    get_events,
    get_health_snapshot,
    get_logs,
    get_start_timestamp,
    is_bot_running,
    set_bot_running,
)

def setup_routes(app):
    @app.get("/")
    def index():
        return render_template("dashboard.html")

    @app.get("/api/status")
    def api_status():
        import time
        uptime = int(time.time() - get_start_timestamp())
        counters = get_counters()
        return jsonify({
            "uptime": uptime,
            "received": counters.get("received", 0),
            "parsed": counters.get("parsed", 0),
            "sent": counters.get("sent", 0),
            "rejected": counters.get("rejected", 0),
            "updates": counters.get("updates", 0),
            "by_market": get_by_market(),
            "running": is_bot_running(),
        })

    @app.get("/api/health")
    def api_health():
        return jsonify(get_health_snapshot())

    @app.get("/api/logs")
    def api_logs():
        return jsonify(get_logs())

    @app.get("/api/events")
    def api_events():
        return jsonify(get_events())

    @app.post("/api/bot/start")
    def api_bot_start():
        message = "ربات از قبل فعال بود."
        if not is_bot_running():
            set_bot_running(True)
            message = "ربات با موفقیت فعال شد."
            add_event("🟢 ربات از طریق داشبورد فعال شد و در حال شنود است.", "success")
        return jsonify({"ok": True, "running": is_bot_running(), "message": message})

    @app.post("/api/bot/stop")
    def api_bot_stop():
        message = "ربات از قبل متوقف شده بود."
        if is_bot_running():
            set_bot_running(False)
            message = "ربات موقتا متوقف شد."
            add_event("🛑 ربات از طریق داشبورد متوقف شد و شنود متوقف گردید.", "warning")
        return jsonify({"ok": True, "running": is_bot_running(), "message": message})

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
