from signal_bot import parse_signal, CHANNEL_PROFILES


def test_rr_omitted_when_chat_in_skip_rr_for():
    chat_id = 9999
    profile = {"skip_rr_for": [chat_id]}
    CHANNEL_PROFILES[chat_id] = profile

    message = """#XAUUSD\nBuy\nEntry Price : 1900\nTP1 : 1910\nStop Loss : 1895"""
    result = parse_signal(message, chat_id, profile)

    assert "R/R" not in result

    CHANNEL_PROFILES.clear()

