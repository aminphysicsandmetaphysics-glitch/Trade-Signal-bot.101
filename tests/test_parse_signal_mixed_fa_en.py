from signal_bot import parse_signal


def test_parse_signal_mixed_fa_en_reply_and_units():
    message = (
        "In reply to John\n"
        "#XAUUSD\n"
        "Buy\n"
        "Entry ۱٬۹۰۰٫۵۰\n"
        "SL ۱۸۹۵\n"
        "TP1: ۱۹۱۰ ۵۰ pips\n"
        "TP2: 1915 30 pts\n"
        "TP3: 1920 1%"
    )
    expected = (
        "📊 #XAUUSD\n"
        "📉 Position: Buy\n"
        "❗️ R/R : 1/1.73\n"
        "💲 Entry Price : 1900.50\n"
        "✔️ TP1 : 1910\n"
        "✔️ TP2 : 1915\n"
        "✔️ TP3 : 1920\n"
        "🚫 Stop Loss : 1895"
    )
    assert parse_signal(message, 1234, {}) == expected
