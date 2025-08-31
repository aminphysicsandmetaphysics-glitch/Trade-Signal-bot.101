import importlib
import pytest


def _load_app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test")
    app = importlib.reload(importlib.import_module("app"))
    return app


@pytest.mark.parametrize(
    "url, method, kwargs",
    [
        ("/save_config", "post", {}),
        ("/start_bot", "post", {}),
        ("/stop_bot", "post", {}),
        ("/api/profiles", "post", {"json": {"name": "p"}}),
        ("/api/profiles/demo/test", "post", {"json": {"message": "hi"}}),
    ],
)
def test_missing_csrf_rejected(monkeypatch, url, method, kwargs):
    app = _load_app(monkeypatch)
    with app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["logged_in"] = True
        resp = getattr(client, method)(url, **kwargs)
        assert resp.status_code == 400

