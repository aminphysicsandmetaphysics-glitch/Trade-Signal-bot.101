import os
import importlib

os.environ.setdefault("SESSION_SECRET", "test")

from profiles import ProfileStore


def test_api_profile_test_handles_missing_profile_options(tmp_path):
    app_module = importlib.reload(importlib.import_module("app"))
    app_module.profiles_store = ProfileStore(tmp_path / "profiles.json")
    app_module._load_profiles_into_channel_profiles()
    app = app_module.app
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()
    resp_create = client.post(
        "/api/profiles",
        json={"name": "dummy", "parse_options": {}},
    )
    assert resp_create.status_code == 201
    resp = client.post("/api/profiles/dummy/test", json={"message": "test"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "parsed" in data
