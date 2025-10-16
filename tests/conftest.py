import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _restore_deque(target, snapshot):
    target.clear()
    target.extend(snapshot)


def _restore_dict(target, snapshot):
    target.clear()
    target.update(snapshot)


def _default_counters():
    return {"received": 0, "parsed": 0, "sent": 0, "rejected": 0, "updates": 0}


def _reset_runtime_state(state_module):
    _restore_dict(state_module.counters, _default_counters())
    state_module.logs.clear()
    state_module.events.clear()
    state_module.bot_state.clear()
    state_module.bot_state.update({"running": True})


@pytest.fixture(autouse=True)
def runtime_state_guard():
    """Reset the in-memory runtime state between tests."""

    from signal_bot import state

    counters_snapshot = dict(state.counters)
    logs_snapshot = list(state.logs)
    events_snapshot = list(state.events)
    bot_state_snapshot = dict(state.bot_state)

    _reset_runtime_state(state)

    yield

    _restore_dict(state.counters, counters_snapshot)
    _restore_deque(state.logs, logs_snapshot)
    _restore_deque(state.events, events_snapshot)
    _restore_dict(state.bot_state, bot_state_snapshot)
