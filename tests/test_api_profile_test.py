import importlib


def test_api_profile_test_handles_missing_profile_options(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test")
    monkeypatch.setenv("PROFILE_STORE_PATH", str(tmp_path / "profiles.json"))
    app_module = importlib.reload(importlib.import_module("app"))
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
