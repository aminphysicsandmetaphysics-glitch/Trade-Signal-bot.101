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
