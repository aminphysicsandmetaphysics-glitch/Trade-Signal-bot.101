import asyncio
from datetime import datetime, timezone

import signal_bot as sb
from signal_bot import SignalBot


class DummyClient:
    def __init__(self):
        self.sent = []

    async def send_message(self, dest, message):
        self.sent.append((dest, message))


class DummyMsg:
    def __init__(self, text):
        self.message = text
        self.date = datetime.now(timezone.utc)
        self.id = 1
        self.media = None


class DummyEvent:
    def __init__(self, chat_id, text):
        self.chat_id = chat_id
        self.message = DummyMsg(text)


def test_handle_new_message_applies_template(monkeypatch):
    profiles = {"default": {111: {"dests": [222], "template": "vip.j2"}}}
    bot = SignalBot(1, "hash", "session", [111], [], profiles=profiles)
    bot.client = DummyClient()
    monkeypatch.setattr(sb, "parse_signal", lambda text, chat_id, profile: text)
    asyncio.run(bot._handle_new_message(DummyEvent(111, "hello")))
    assert bot.client.sent == [(-100222, "[VIP] hello")]
