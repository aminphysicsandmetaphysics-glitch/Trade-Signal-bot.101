import sqlite3

from signal_bot import state


class _FlakyConnection:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.calls = 0

    def execute(self, sql: str, params=()):
        if self.calls == 0:
            self.calls += 1
            raise sqlite3.OperationalError("database is locked")
        return self._conn.execute(sql, params)


def test_execute_retries_on_locked():
    state._ensure_initialised()
    with state._connection() as conn:
        flaky_conn = _FlakyConnection(conn)
        cursor = state._execute(flaky_conn, "SELECT 1")
        assert cursor.fetchone()[0] == 1
        assert flaky_conn.calls == 1
