import asyncio
from datetime import datetime, timezone

import signal_bot
from signal_bot import SignalBot


class DummyMsg:
    def __init__(self, mid, text):
        self.id = mid
        self.message = text
        self.date = datetime.now(timezone.utc)


class DummyEvent:
    def __init__(self, chat_id, text):
        self.chat_id = chat_id
        self.message = DummyMsg(1, text)


def test_handle_new_message_normalizes_once(monkeypatch):
    bot = SignalBot(1, "hash", "sess", [], [])

    calls = []
    orig_normalize = signal_bot.normalize_numbers

    def fake_normalize(text: str) -> str:
        calls.append(text)
        return orig_normalize(text)

    monkeypatch.setattr(signal_bot, "normalize_numbers", fake_normalize)

    def fake_parse_signal(text, chat_id, profile):
        assert text == "۱۲۳۴"
        return fake_normalize(text)

    monkeypatch.setattr(signal_bot, "parse_signal", fake_parse_signal)

    event = DummyEvent(123, "۱۲۳۴")
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(bot._handle_new_message(event))
    finally:
        loop.close()

    assert calls == ["۱۲۳۴"]
