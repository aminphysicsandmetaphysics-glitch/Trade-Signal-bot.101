import importlib


def test_start_bot_invalid_api_id(monkeypatch):
    """Posting to /start_bot with a non-int api_id returns 400 and flashes."""
    monkeypatch.setenv("SESSION_SECRET", "test")
    monkeypatch.setenv("ADMIN_USER", "u")
    monkeypatch.setenv("ADMIN_PASS", "p")
    app = importlib.reload(importlib.import_module("app"))

    # Populate config with required fields but invalid api_id
    app.config_store.update(
        {
            "api_id": "notanint",
            "api_hash": "hash",
            "session_string": "session",
            "from_channels": "",
            "to_channels": "dest",
        }
    )
    app.bot_instance = None

    with app.app.test_client() as client:
        client.post("/login", data={"username": "u", "password": "p"})
        response = client.post("/start_bot")
        assert response.status_code == 400
        with client.session_transaction() as sess:
            flashes = sess.get("_flashes", [])
        assert any(
            category == "error" and "API ID must be an integer." in msg
            for category, msg in flashes
        )
    assert app.bot_instance is None

