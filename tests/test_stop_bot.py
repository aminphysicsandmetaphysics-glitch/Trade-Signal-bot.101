import asyncio
from concurrent.futures import Future
import importlib


def _load_app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test")
    monkeypatch.setenv("ADMIN_USER", "u")
    monkeypatch.setenv("ADMIN_PASS", "p")
    return importlib.reload(importlib.import_module("app"))


def test_stop_bot_route_disconnects_cleanly(monkeypatch):
    app = _load_app(monkeypatch)

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

    monkeypatch.setattr(
        asyncio, "run_coroutine_threadsafe", fake_run_coroutine_threadsafe
    )

    client = app.app.test_client()
    with client.session_transaction() as sess:
        sess["logged_in"] = True
    resp = client.post("/stop_bot")
    assert resp.status_code == 302
    assert fake_bot.stopped
    assert calls["count"] == 1
    loop.close()


def test_stop_bot_requires_login(monkeypatch):
    app = _load_app(monkeypatch)
    client = app.app.test_client()
    resp = client.post("/stop_bot")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

