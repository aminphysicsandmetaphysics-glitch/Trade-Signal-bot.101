from signal_bot import normalize_numbers, strip_invisibles


def test_normalize_numbers_removes_commas():
    assert normalize_numbers("۱۲۳,۴۵۶") == "123456"
    assert normalize_numbers("1,234") == "1234"


def test_normalize_numbers_farsi_with_separators():
    assert normalize_numbers("۱٬۲۳۴٬۵۶۷٫۸۹") == "1234567.89"


def test_normalize_numbers_arabic_with_separators():
    assert normalize_numbers("١٬٢٣٤٬٥٦٧٫٨٩") == "1234567.89"


def test_normalize_numbers_with_emojis_and_farsi_separators():
    text = "📈۱٬۲۳۴٬۵۶۷٫۸۹📉"
    assert normalize_numbers(text) == "📈1234567.89📉"
    assert normalize_numbers("💰۱۲۳۴۵۶💎") == "💰123456💎"


def test_strip_invisibles_handles_emoji_and_bidi():
    text = "\u2066💎#EURUSD💎\u2069"
    assert strip_invisibles(normalize_numbers(text)) == "#EURUSD"
