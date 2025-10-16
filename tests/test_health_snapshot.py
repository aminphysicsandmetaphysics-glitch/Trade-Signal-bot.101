from signal_bot.state import (
    add_event,
    add_log_entry,
    counters,
    events,
    get_health_snapshot,
    logs,
)


def test_health_snapshot_ok_state():
    # runtime state is reset by the autouse fixture in conftest
    snapshot = get_health_snapshot()

    assert snapshot["healthy"] is True
    assert snapshot["status"] == "ok"
    assert snapshot["running"] is True
    assert snapshot["events"]["total"] == len(events)
    assert snapshot["events"]["last_error"] is None
    assert snapshot["events"]["last_warning"] is None
    assert snapshot["logs"]["total"] == 0
    assert snapshot["logs"]["last_entry"] is None
    assert snapshot["logs"]["pending_unsent"] is None
    assert snapshot["counters"] == counters


def test_health_snapshot_with_warning():
    add_event("هشدار تست", "warning")
    snapshot = get_health_snapshot()

    assert snapshot["status"] == "warning"
    assert snapshot["healthy"] is False
    assert snapshot["events"]["last_warning"]["message"] == "هشدار تست"
    assert snapshot["events"]["last_error"] is None


def test_health_snapshot_with_error_and_pending_log():
    add_event("هشدار تست", "warning")
    add_log_entry(symbol="BTCUSDT", market="crypto", side="long", rr="1/2", sent=False)
    add_event("خطای تست", "error")

    snapshot = get_health_snapshot()

    assert snapshot["status"] == "error"
    assert snapshot["healthy"] is False
    assert snapshot["events"]["last_error"]["message"] == "خطای تست"
    assert snapshot["logs"]["last_entry"]["symbol"] == "BTCUSDT"
    assert snapshot["logs"]["pending_unsent"]["sent"] is False
    assert snapshot["logs"]["pending_unsent"]["symbol"] == "BTCUSDT"
