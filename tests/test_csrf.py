import importlib
import tempfile

import pytest

from profiles import ProfileStore


def _load_app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test")
    app_module = importlib.reload(importlib.import_module("app"))
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    app_module.profiles_store = ProfileStore(tmp.name)
    app_module._load_profiles_into_channel_profiles()
    return app_module


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

