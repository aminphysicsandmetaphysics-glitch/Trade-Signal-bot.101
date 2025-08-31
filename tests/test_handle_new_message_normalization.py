import asyncio
import logging
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

    def fake_parse_signal(text, chat_id, profile, *, return_meta=False):
        assert text == "۱۲۳۴"
        result = fake_normalize(text)
        if return_meta:
            return result, {"symbol": "", "position": ""}
        return result

    monkeypatch.setattr(signal_bot, "parse_signal", fake_parse_signal)

    event = DummyEvent(123, "۱۲۳۴")
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(bot._handle_new_message(event))
    finally:
        loop.close()

    assert calls == ["۱۲۳۴"]


def test_handle_new_message_strips_invisibles_and_emojis(monkeypatch):
    bot = SignalBot(1, "hash", "sess", [], [])

    captured = {}

    def fake_parse_signal(text, chat_id, profile, *, return_meta=True):
        cleaned = signal_bot.strip_invisibles(signal_bot.normalize_numbers(text))
        captured["text"] = cleaned
        return cleaned, {"symbol": "", "position": ""}

    monkeypatch.setattr(signal_bot, "parse_signal", fake_parse_signal)

    text = "\u2066🔥#EURUSD🔥\u2069"
    event = DummyEvent(123, text)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(bot._handle_new_message(event))
    finally:
        loop.close()

    assert captured["text"] == "#EURUSD"


def test_handle_new_message_handles_malformed_parse(monkeypatch, caplog):
    bot = SignalBot(1, "hash", "sess", [], [])

    def bad_parse(text, chat_id, profile, *, return_meta=True):
        return "oops"

    monkeypatch.setattr(signal_bot, "parse_signal", bad_parse)

    event = DummyEvent(123, "hi")
    loop = asyncio.new_event_loop()
    try:
        with caplog.at_level(logging.ERROR):
            loop.run_until_complete(bot._handle_new_message(event))
    finally:
        loop.close()

    assert bot.stats.rejected == 1
    assert bot.stats.parsed == 0
    assert "Unexpected parse_signal return" in caplog.text
