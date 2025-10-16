import pytest
from flask import Flask

from signal_bot import state
from signal_bot.web import setup_routes


def create_app():
    app = Flask(__name__)
    setup_routes(app)
    return app


def test_stop_and_start_toggle_runtime_state():
    app = create_app()
    client = app.test_client()

    # default state starts with the bot running
    assert state.is_bot_running() is True

    stop_response = client.post("/api/bot/stop")
    assert stop_response.status_code == 200
    stop_payload = stop_response.get_json()
    assert stop_payload["ok"] is True
    assert stop_payload["running"] is False
    assert "ربات موقتا متوقف شد." in stop_payload["message"]
    assert state.is_bot_running() is False

    events = state.get_events()
    assert events, "expected an event to be recorded after stopping the bot"
    assert events[0]["message"].startswith("🛑 ربات از طریق داشبورد متوقف شد")

    start_response = client.post("/api/bot/start")
    assert start_response.status_code == 200
    start_payload = start_response.get_json()
    assert start_payload["ok"] is True
    assert start_payload["running"] is True
    assert "ربات با موفقیت فعال شد." in start_payload["message"]
    assert state.is_bot_running() is True

    events_after_start = state.get_events()
    assert events_after_start[0]["message"].startswith("🟢 ربات از طریق داشبورد فعال شد")
    # stop event should still be present just after the start event
    assert any(event["message"].startswith("🛑 ربات از طریق داشبورد متوقف شد") for event in events_after_start)


def test_toggle_endpoints_are_idempotent():
    app = create_app()
    client = app.test_client()

    # ensure bot is stopped before calling the stop endpoint again
    state.set_bot_running(False)
    events_before = state.get_events()

    repeated_stop = client.post("/api/bot/stop")
    assert repeated_stop.status_code == 200
    stop_payload = repeated_stop.get_json()
    assert stop_payload["running"] is False
    assert stop_payload["message"] == "ربات از قبل متوقف شده بود."
    assert state.is_bot_running() is False
    assert len(state.get_events()) == len(events_before)

    # bring bot back to running and call start twice
    state.set_bot_running(True)
    events_before_start = state.get_events()

    repeated_start = client.post("/api/bot/start")
    assert repeated_start.status_code == 200
    start_payload = repeated_start.get_json()
    assert start_payload["running"] is True
    assert start_payload["message"] == "ربات از قبل فعال بود."
    assert state.is_bot_running() is True
    assert len(state.get_events()) == len(events_before_start)
