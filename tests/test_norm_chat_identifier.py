import pytest
from signal_bot import _norm_chat_identifier, SignalBot


def test_norm_chat_identifier_numeric_string():
    assert _norm_chat_identifier("12345") == -10012345


def test_norm_chat_identifier_negative_string():
    assert _norm_chat_identifier("-10012345") == -10012345


def test_norm_chat_identifier_username():
    assert _norm_chat_identifier("@mychannel") == "mychannel"


def test_norm_chat_identifier_url_numeric():
    assert _norm_chat_identifier("https://t.me/12345") == -10012345


def test_signalbot_normalizes_string_ids():
    bot = SignalBot(1, "hash", "session", ["12345"], ["67890"])
    assert bot.from_channels == [-10012345]
    assert bot.to_channels == [-10067890]
