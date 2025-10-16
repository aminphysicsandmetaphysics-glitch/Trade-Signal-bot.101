import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Use an isolated database for tests so that the development/runtime database is
# never touched when running the suite.
TEST_DB_PATH = ROOT / "test-state.sqlite3"
os.environ.setdefault("STATE_DB_PATH", str(TEST_DB_PATH))


@pytest.fixture(autouse=True)
def runtime_state_guard():
    """Reset the persisted runtime state between tests."""

    from signal_bot import state

    state.reset_state()
    yield
    state.reset_state()
