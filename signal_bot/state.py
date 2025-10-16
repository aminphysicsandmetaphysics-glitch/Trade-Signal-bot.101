"""Runtime state management for the Trade Signal bot.

The original implementation kept all counters, events, logs and bot status in
module level mutable objects. That approach only works reliably when the web
application and the Telegram worker run inside the same Python process. In a
production deployment (for example on Render) the two components often run in
separate processes which means in-memory data structures are not shared. As a
result the dashboard would always see empty buffers and the on/off toggle would
affect only the process that served the HTTP request.

To make the dashboard functional regardless of the deployment layout we persist
the runtime state in a lightweight SQLite database. Every read/write operation
goes through this module which keeps the API surface close to the previous
version while ensuring that all processes observe the same state.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional

MAX_LOG_ENTRIES = 100
MAX_EVENT_ENTRIES = 200

_DB_PATH = os.environ.get("STATE_DB_PATH")
if not _DB_PATH:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    _DB_PATH = os.path.join(base_dir, "state-data.sqlite3")

_INIT_LOCK = threading.Lock()
_INITIALISED = False


def _now() -> datetime:
    """Return a timezone-aware datetime in UTC."""

    return datetime.now(timezone.utc)


def _timestamp_payload() -> Dict[str, Any]:
    now = _now()
    return {
        "ts": now.isoformat(),
        "ts_epoch": int(now.timestamp()),
    }


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode and configure a generous busy timeout so concurrent
    # readers/writers from different processes do not fail with
    # ``sqlite3.OperationalError: database is locked``.  This is particularly
    # important for the dashboard endpoints which frequently open short-lived
    # connections in parallel with the worker process updating the state.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _execute(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
    return conn.execute(sql, params)


def _ensure_initialised() -> None:
    global _INITIALISED
    if _INITIALISED:
        return
    with _INIT_LOCK:
        if _INITIALISED:
            return
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        with _connection() as conn:
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS counters (
                    key TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                )
                """,
            )
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS by_market (
                    key TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                )
                """,
            )
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    ts_epoch INTEGER NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL
                )
                """,
            )
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    ts_epoch INTEGER NOT NULL,
                    symbol TEXT,
                    market TEXT,
                    side TEXT,
                    rr TEXT,
                    sent INTEGER NOT NULL
                )
                """,
            )
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """,
            )

            if _get_meta(conn, "start_ts") is None:
                _set_meta(conn, "start_ts", str(time.time()))

            if _get_meta(conn, "running") is None:
                _set_meta(conn, "running", "1")

            events_count = _execute(conn, "SELECT COUNT(*) AS c FROM events").fetchone()["c"]
            if events_count == 0:
                _insert_event(conn, "🟢 راه‌اندازی اولیه سرویس ثبت شد.", "success")

        _INITIALISED = True


def _get_meta(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    row = _execute(conn, "SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return row["value"]


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    _execute(
        conn,
        "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _trim_table(conn: sqlite3.Connection, table: str, limit: int) -> None:
    _execute(
        conn,
        f"DELETE FROM {table} WHERE id NOT IN (SELECT id FROM {table} ORDER BY id DESC LIMIT ?)",
        (limit,),
    )


def _insert_event(conn: sqlite3.Connection, message: str, level: str) -> Dict[str, Any]:
    payload = {
        **_timestamp_payload(),
        "message": message,
        "level": level,
    }
    _execute(
        conn,
        "INSERT INTO events (ts, ts_epoch, level, message) VALUES (?, ?, ?, ?)",
        (
            payload["ts"],
            payload["ts_epoch"],
            payload["level"],
            payload["message"],
        ),
    )
    _trim_table(conn, "events", MAX_EVENT_ENTRIES)
    return payload


def _insert_log(
    conn: sqlite3.Connection,
    *,
    symbol: Optional[str],
    market: Optional[str],
    side: Optional[str],
    rr: Optional[str],
    sent: bool,
) -> Dict[str, Any]:
    payload = {
        **_timestamp_payload(),
        "symbol": symbol,
        "market": market,
        "side": side,
        "rr": rr,
        "sent": bool(sent),
    }
    _execute(
        conn,
        """
        INSERT INTO logs (ts, ts_epoch, symbol, market, side, rr, sent)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["ts"],
            payload["ts_epoch"],
            payload["symbol"],
            payload["market"],
            payload["side"],
            payload["rr"],
            1 if payload["sent"] else 0,
        ),
    )
    _trim_table(conn, "logs", MAX_LOG_ENTRIES)
    return payload


def reset_state() -> None:
    """Reset the persisted runtime state.

    This helper is primarily intended for tests. It clears all counters, logs and
    events, resets the bot to the running state and records a new startup event.
    """

    _ensure_initialised()
    with _connection() as conn:
        _execute(conn, "DELETE FROM counters")
        _execute(conn, "DELETE FROM by_market")
        _execute(conn, "DELETE FROM logs")
        _execute(conn, "DELETE FROM events")
        _set_meta(conn, "running", "1")
        _set_meta(conn, "start_ts", str(time.time()))
        _insert_event(conn, "🟢 راه‌اندازی اولیه سرویس ثبت شد.", "success")


def add_event(message: str, level: str = "info") -> Dict[str, Any]:
    _ensure_initialised()
    with _connection() as conn:
        return _insert_event(conn, message, level)


def add_log_entry(
    *,
    symbol: Optional[str],
    market: Optional[str],
    side: Optional[str],
    rr: Optional[str],
    sent: bool,
) -> Dict[str, Any]:
    _ensure_initialised()
    with _connection() as conn:
        return _insert_log(
            conn,
            symbol=symbol,
            market=market,
            side=side,
            rr=rr,
            sent=sent,
        )


def _row_to_event(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "ts": row["ts"],
        "ts_epoch": row["ts_epoch"],
        "level": row["level"],
        "message": row["message"],
    }


def _row_to_log(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "ts": row["ts"],
        "ts_epoch": row["ts_epoch"],
        "symbol": row["symbol"],
        "market": row["market"],
        "side": row["side"],
        "rr": row["rr"],
        "sent": bool(row["sent"]),
    }


def get_events(limit: int = MAX_EVENT_ENTRIES) -> list[Dict[str, Any]]:
    _ensure_initialised()
    with _connection() as conn:
        cur = _execute(
            conn,
            "SELECT ts, ts_epoch, level, message FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [_row_to_event(row) for row in cur.fetchall()]


def get_logs(limit: int = MAX_LOG_ENTRIES) -> list[Dict[str, Any]]:
    _ensure_initialised()
    with _connection() as conn:
        cur = _execute(
            conn,
            "SELECT ts, ts_epoch, symbol, market, side, rr, sent FROM logs ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [_row_to_log(row) for row in cur.fetchall()]


def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    return _execute(conn, f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]


def get_counters() -> Dict[str, int]:
    _ensure_initialised()
    defaults = {"received": 0, "parsed": 0, "sent": 0, "rejected": 0, "updates": 0}
    with _connection() as conn:
        cur = _execute(conn, "SELECT key, value FROM counters")
        for row in cur.fetchall():
            defaults[row["key"]] = row["value"]
    return defaults


def get_by_market() -> Dict[str, int]:
    _ensure_initialised()
    defaults = {"crypto": 0, "forex": 0, "gold": 0}
    with _connection() as conn:
        cur = _execute(conn, "SELECT key, value FROM by_market")
        for row in cur.fetchall():
            defaults[row["key"]] = row["value"]
    return defaults


def increment_counter(name: str, amount: int = 1) -> None:
    _ensure_initialised()
    with _connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO counters(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = value + ?
            """,
            (name, amount, amount),
        )


def increment_market_counter(name: str, amount: int = 1) -> None:
    _ensure_initialised()
    with _connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO by_market(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = value + ?
            """,
            (name, amount, amount),
        )


def is_bot_running() -> bool:
    _ensure_initialised()
    with _connection() as conn:
        value = _get_meta(conn, "running", "1")
    return value == "1"


def set_bot_running(running: bool) -> None:
    _ensure_initialised()
    with _connection() as conn:
        _set_meta(conn, "running", "1" if running else "0")


def get_start_timestamp() -> float:
    _ensure_initialised()
    with _connection() as conn:
        value = _get_meta(conn, "start_ts", str(time.time()))
        if value is None:
            value = str(time.time())
            _set_meta(conn, "start_ts", value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return time.time()


def _find_event_by_level(level: str) -> Optional[Dict[str, Any]]:
    _ensure_initialised()
    with _connection() as conn:
        row = _execute(
            conn,
            "SELECT ts, ts_epoch, level, message FROM events WHERE level = ? ORDER BY id DESC LIMIT 1",
            (level,),
        ).fetchone()
    return _row_to_event(row) if row else None


def _find_first_unsent_log() -> Optional[Dict[str, Any]]:
    _ensure_initialised()
    with _connection() as conn:
        row = _execute(
            conn,
            "SELECT ts, ts_epoch, symbol, market, side, rr, sent FROM logs WHERE sent = 0 ORDER BY id DESC LIMIT 1",
        ).fetchone()
    return _row_to_log(row) if row else None


def get_health_snapshot() -> Dict[str, Any]:
    """Return a structured view over the persisted runtime state."""

    last_error = _find_event_by_level("error")
    last_warning = _find_event_by_level("warning")
    logs = get_logs(limit=1)
    last_log = logs[0] if logs else None
    pending_unsent = _find_first_unsent_log()

    status = "ok"
    if last_error:
        status = "error"
    elif last_warning:
        status = "warning"

    _ensure_initialised()
    with _connection() as conn:
        events_total = _count_rows(conn, "events")
        logs_total = _count_rows(conn, "logs")

    return {
        "healthy": status == "ok",
        "status": status,
        "running": is_bot_running(),
        "counters": get_counters(),
        "events": {
            "total": events_total,
            "last_error": last_error,
            "last_warning": last_warning,
        },
        "logs": {
            "total": logs_total,
            "last_entry": last_log,
            "pending_unsent": pending_unsent,
        },
    }


# Initialise on import so that unit tests that import this module get a fully
# prepared backing store without having to call any helper explicitly.
_ensure_initialised()

