import logging
from datetime import datetime, timedelta, timezone

import asyncio

from signal_bot import SignalBot


class DummyMsg:
    def __init__(self, mid, text):
        self.id = mid
        self.message = text


def test_fresh_enough_logs_stale(caplog):
    bot = SignalBot(1, 'hash', 'sess', [], [])
    bot.startup_time = datetime.now(timezone.utc)
    bot.grace = timedelta(minutes=1)
    stale_dt = bot.startup_time - timedelta(minutes=2)
    with caplog.at_level("DEBUG"):
        assert not bot._fresh_enough(stale_dt)
    assert any("Ignoring stale message" in r.message for r in caplog.records)


def test_dedup_logs_duplicate(caplog):
    bot = SignalBot(1, 'hash', 'sess', [], [])
    msg = DummyMsg(1, "hello")
    with caplog.at_level("DEBUG"):
        assert bot._dedup_and_remember(123, msg) is False
        assert bot._dedup_and_remember(123, msg) is True
    assert any("Discarding duplicate" in r.message for r in caplog.records)


class DummyEvent:
    def __init__(self, chat_id, text):
        self.chat_id = chat_id
        self.message = DummyMsg(1, text)
        # ensure message has date attribute
        self.message.date = datetime.now(timezone.utc)


def test_logs_rejected_message(caplog):
    bot = SignalBot(1, 'hash', 'sess', [], [])
    event = DummyEvent(123, "hello world")
    loop = asyncio.new_event_loop()
    try:
        with caplog.at_level("INFO"):
            loop.run_until_complete(bot._handle_new_message(event))
    finally:
        loop.close()
    assert any(
        "Rejecting message from 123" in r.message and "hello world" in r.message
        for r in caplog.records
    )
