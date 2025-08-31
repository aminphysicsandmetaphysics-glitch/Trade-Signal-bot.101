import importlib
import pytest


@pytest.fixture
def app_module(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test")
    monkeypatch.setenv("ADMIN_USER", "u")
    monkeypatch.setenv("ADMIN_PASS", "p")
    return importlib.reload(importlib.import_module("app"))


def test_parse_from_channels_numeric_strings(app_module):
    assert app_module.parse_from_channels("123, -456, foo") == [123, -456, "foo"]
    assert app_module.parse_from_channels("123 -456 foo") == [123, -456, "foo"]


def test_parse_to_channels_json_numeric_strings(app_module):
    assert app_module.parse_to_channels('["123", "-456", "foo"]') == [123, -456, "foo"]
