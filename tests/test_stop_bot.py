import asyncio
from concurrent.futures import Future
import importlib


def test_stop_bot_route_disconnects_cleanly(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test")
    monkeypatch.setenv("ADMIN_USER", "u")
    monkeypatch.setenv("ADMIN_PASS", "p")
    app = importlib.reload(importlib.import_module("app"))
    app.app.config["WTF_CSRF_ENABLED"] = False

    class DummyLoop:
        def is_running(self):
            return True

    loop = DummyLoop()

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
            result = asyncio.run(coro)
        except Exception as e:
            fut.set_exception(e)
        else:
            fut.set_result(result)
        return fut

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", fake_run_coroutine_threadsafe)

    client = app.app.test_client()
    with client.session_transaction() as sess:
        sess["logged_in"] = True
    resp = client.post("/stop_bot")
    assert resp.status_code == 302
    assert fake_bot.stopped
    assert calls["count"] == 1


def test_stop_bot_no_loop_does_not_crash(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test")
    monkeypatch.setenv("ADMIN_USER", "u")
    monkeypatch.setenv("ADMIN_PASS", "p")
    app = importlib.reload(importlib.import_module("app"))
    app.app.config["WTF_CSRF_ENABLED"] = False

    class FakeBot:
        loop = None
        def is_running(self):
            return True
        async def stop(self):
            raise AssertionError("stop should not be awaited")

    fake_bot = FakeBot()
    monkeypatch.setattr(app, "bot_instance", fake_bot)

    calls = {"count": 0}

    def fake_run_coroutine_threadsafe(*args, **kwargs):
        calls["count"] += 1
        raise AssertionError("run_coroutine_threadsafe should not be called")

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", fake_run_coroutine_threadsafe)

    client = app.app.test_client()
    with client.session_transaction() as sess:
        sess["logged_in"] = True
    resp = client.post("/stop_bot")
    assert resp.status_code == 302
    assert calls["count"] == 0

