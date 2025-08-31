import importlib


def _load_app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test")
    monkeypatch.setenv("ADMIN_USER", "u")
    monkeypatch.setenv("ADMIN_PASS", "p")
    app = importlib.reload(importlib.import_module("app"))
    app.app.config["WTF_CSRF_ENABLED"] = False
    return app


def test_login_required(monkeypatch):
    app = _load_app(monkeypatch)
    with app.app.test_client() as client:
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
        client.post("/login", data={"username": "u", "password": "p"})
        resp = client.get("/")
        assert resp.status_code == 200


def test_stop_bot_requires_login(monkeypatch):
    app = _load_app(monkeypatch)
    with app.app.test_client() as client:
        resp = client.post("/stop_bot")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
        client.post("/login", data={"username": "u", "password": "p"})
        resp = client.post("/stop_bot")
        # successful stop redirects back to index
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/")
