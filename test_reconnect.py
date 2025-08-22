import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from signal_bot import SignalBot


def test_reconnect_loop_continues_on_failure():
    init_calls = {'count': 0}
    run_calls = {'count': 0}

    class FakeTelegramClient:
        def __init__(self, *args, **kwargs):
            init_calls['count'] += 1
            self.loop = asyncio.get_event_loop()

        def on(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def start(self):
            pass

        async def get_entity(self, c):
            return SimpleNamespace(title='dummy', id=c)

        def run_until_disconnected(self):
            run_calls['count'] += 1
            raise ConnectionError('network down')

        async def connect(self):
            raise ConnectionError('still down')

        async def disconnect(self):
            pass

        async def is_connected(self):
            return False

    fake_events = SimpleNamespace(NewMessage=lambda *a, **k: (lambda f: f))
    fake_session = lambda s: s

    with patch('signal_bot.TelegramClient', FakeTelegramClient), \
         patch('signal_bot.events', fake_events), \
         patch('signal_bot.StringSession', fake_session):
        bot = SignalBot(1, 'hash', 'session', [], [], retry_delay=0, max_retries=2)
        bot.start()

    assert run_calls['count'] == 2
    assert init_calls['count'] == 2
