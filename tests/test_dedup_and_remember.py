from types import SimpleNamespace

from signal_bot import SignalBot


def make_bot():
    return SignalBot(1, "hash", "session", [], [])


def test_duplicate_message_id_returns_true_for_repeat_and_false_for_new():
    bot = make_bot()
    src = 123
    msg = SimpleNamespace(id=1, message="hello")
    assert bot._dedup_and_remember(src, msg) is False

    # Same ID and content should be considered duplicate
    dup_msg = SimpleNamespace(id=1, message="hello")
    assert bot._dedup_and_remember(src, dup_msg) is True

    # New ID and content should not be considered duplicate
    new_msg = SimpleNamespace(id=2, message="world")
    assert bot._dedup_and_remember(src, new_msg) is False


def test_duplicate_content_returns_true_for_repeat_and_false_for_new():
    bot = make_bot()
    src = 456
    msg = SimpleNamespace(id=10, message="same content")
    assert bot._dedup_and_remember(src, msg) is False

    # Different ID but same content should be considered duplicate
    dup_content_msg = SimpleNamespace(id=11, message="same content")
    assert bot._dedup_and_remember(src, dup_content_msg) is True

    # Completely new content should not be considered duplicate
    new_content_msg = SimpleNamespace(id=12, message="different content")
    assert bot._dedup_and_remember(src, new_content_msg) is False
