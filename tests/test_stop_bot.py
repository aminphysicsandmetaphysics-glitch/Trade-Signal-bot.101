import asyncio
from concurrent.futures import Future
import importlib


def test_stop_bot_route_disconnects_cleanly(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test")
    monkeypatch.setenv("ADMIN_USER", "u")
    monkeypatch.setenv("ADMIN_PASS", "p")
    app = importlib.import_module("app")

    loop = asyncio.new_event_loop()

    class FakeBot:
        def __init__(self, loop):
            self.loop = loop
            self.stopped = False
        def is_running(self):
            return True
        async def stop(self):
            self.stopped = True

    fake_bot = FakeBot(loop)
    monkeypatch.setattr(app, "bot_instance", fake_bot)

    calls = {"count": 0}

    def fake_run_coroutine_threadsafe(coro, loop_arg):
        calls["count"] += 1
        assert loop_arg is loop
        fut = Future()
        try:
            result = loop.run_until_complete(coro)
        except Exception as e:
            fut.set_exception(e)
        else:
            fut.set_result(result)
        return fut

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", fake_run_coroutine_threadsafe)

    client = app.app.test_client()
    client.post("/login", data={"username": "u", "password": "p"})
    resp = client.post("/stop_bot")
    assert resp.status_code == 302
    assert fake_bot.stopped
    assert calls["count"] == 1
    loop.close()

