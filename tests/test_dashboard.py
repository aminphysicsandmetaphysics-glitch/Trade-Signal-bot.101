import importlib
import tempfile


def _load_app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test")
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    monkeypatch.setenv("PROFILE_STORE_PATH", tmp.name)
    app = importlib.reload(importlib.import_module("app"))
    app.app.config["WTF_CSRF_ENABLED"] = False
    return app


def test_dashboard_route(monkeypatch):
    app = _load_app(monkeypatch)
    with app.app.test_client() as client:
        resp = client.get("/dashboard")
        assert resp.status_code == 200
