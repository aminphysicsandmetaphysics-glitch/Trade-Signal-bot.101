from collections import deque
from datetime import datetime, timezone
import time

counters = {"received": 0, "parsed": 0, "sent": 0, "rejected": 0, "updates": 0}
by_market = {"crypto": 0, "forex": 0, "gold": 0}
logs = deque(maxlen=100)
events = deque(maxlen=200)
bot_state = {"running": True}
start_ts = time.time()


def _now():
    """Return a timezone-aware datetime in UTC."""
    return datetime.now(timezone.utc)


def _timestamp_payload():
    now = _now()
    return {
        "ts": now.isoformat(),
        "ts_epoch": int(now.timestamp()),
    }


def add_event(message: str, level: str = "info"):
    payload = {
        **_timestamp_payload(),
        "message": message,
        "level": level,
    }
    events.appendleft(payload)


def add_log_entry(*, symbol: str | None, market: str | None, side: str | None, rr: str | None, sent: bool):
    payload = {
        **_timestamp_payload(),
        "symbol": symbol,
        "market": market,
        "side": side,
        "rr": rr,
        "sent": sent,
    }
    logs.appendleft(payload)


add_event("🟢 راه‌اندازی اولیه سرویس ثبت شد.", "success")


def _find_event_by_level(level: str):
    for ev in events:
        if ev.get("level") == level:
            return ev
    return None


def _find_first_unsent_log():
    for entry in logs:
        if not entry.get("sent", False):
            return entry
    return None


def get_health_snapshot():
    """Return a structured view over the in-memory runtime state.

    The snapshot is meant to power lightweight health checks without exposing the
    full event/log buffers. It surfaces high level counters alongside the most
    recent warning/error events and pending log entries so the dashboard (or
    tests) can quickly determine whether everything is operating normally.
    """

    last_error = _find_event_by_level("error")
    last_warning = _find_event_by_level("warning")
    last_log = logs[0] if logs else None
    pending_unsent = _find_first_unsent_log()

    status = "ok"
    if last_error:
        status = "error"
    elif last_warning:
        status = "warning"

    return {
        "healthy": status == "ok",
        "status": status,
        "running": bot_state.get("running", False),
        "counters": dict(counters),
        "events": {
            "total": len(events),
            "last_error": last_error,
            "last_warning": last_warning,
        },
        "logs": {
            "total": len(logs),
            "last_entry": last_log,
            "pending_unsent": pending_unsent,
        },
    }
