from flask import render_template, jsonify, request
from .state import counters, logs, by_market, start_ts

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
        })

    @app.get("/api/logs")
    def api_logs():
        return jsonify(list(logs))

    @app.post("/api/bot/start")
    def api_bot_start():
        return jsonify({"ok": True, "note": "Worker auto-starts at app boot."})

    @app.post("/api/bot/stop")
    def api_bot_stop():
        return jsonify({"ok": True, "note": "Not implemented. Use process control."})
