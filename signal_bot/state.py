from collections import deque
import time

counters = {"received": 0, "parsed": 0, "sent": 0, "rejected": 0, "updates": 0}
by_market = {"crypto": 0, "forex": 0, "gold": 0}
logs = deque(maxlen=100)
start_ts = time.time()
