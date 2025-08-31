import importlib
import tempfile


def _load_app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test")
    monkeypatch.setenv("ADMIN_USER", "u")
    monkeypatch.setenv("ADMIN_PASS", "p")
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    monkeypatch.setenv("PROFILE_STORE_PATH", tmp.name)
    app = importlib.reload(importlib.import_module("app"))
    app.app.config["WTF_CSRF_ENABLED"] = False
    return app


def test_dashboard_route(monkeypatch):
    app = _load_app(monkeypatch)
    with app.app.test_client() as client:
        client.post("/login", data={"username": "u", "password": "p"})
        resp = client.get("/dashboard")
        assert resp.status_code == 200
