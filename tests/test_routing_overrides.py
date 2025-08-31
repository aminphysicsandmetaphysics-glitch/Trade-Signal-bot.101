import asyncio
from datetime import datetime, timezone

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


def _run(bot: SignalBot, event: DummyEvent) -> None:
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(bot._handle_new_message(event))
    finally:
        loop.close()


def test_routing_override_sends_to_route():
    message = "#XAUUSD\nBuy\nEntry Price : 1900\nTP1 : 1910\nStop Loss : 1895"
    bot = SignalBot(1, "hash", "sess", [], [555], routes={"default": {"XAUUSD:BUY": [666]}})
    bot.client = DummyClient()
    _run(bot, DummyEvent(1, message))
    assert [d for d, _ in bot.client.sent] == [-100666]


def test_routing_falls_back_to_default():
    message = "#XAUUSD\nSell\nEntry Price : 1900\nTP1 : 1890\nStop Loss : 1910"
    bot = SignalBot(1, "hash", "sess", [], [555], routes={"default": {"XAUUSD:BUY": [666]}})
    bot.client = DummyClient()
    _run(bot, DummyEvent(1, message))
    assert [d for d, _ in bot.client.sent] == [-100555]
