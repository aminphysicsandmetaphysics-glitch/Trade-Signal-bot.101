from collections import deque
from datetime import datetime
import time

counters = {"received": 0, "parsed": 0, "sent": 0, "rejected": 0, "updates": 0}
by_market = {"crypto": 0, "forex": 0, "gold": 0}
logs = deque(maxlen=100)
events = deque(maxlen=200)
bot_state = {"running": True}
start_ts = time.time()


def _now_str():
    return datetime.now().strftime("%H:%M:%S")


def add_event(message: str, level: str = "info"):
    events.appendleft({
        "ts": _now_str(),
        "message": message,
        "level": level,
    })


add_event("ربات راه‌اندازی شد.")
