import os

os.environ.setdefault("SESSION_SECRET", "test")

from app import app, profiles_store


def test_api_profile_test_handles_missing_profile_options():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    profiles_store["dummy"] = {"parse_options": {}}
    client = app.test_client()
    resp = client.post("/api/profiles/dummy/test", json={"message": "test"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "parsed" in data
    profiles_store.clear()
