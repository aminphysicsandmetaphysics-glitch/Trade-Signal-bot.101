from signal_bot import normalize_numbers


def test_normalize_numbers_removes_commas():
    assert normalize_numbers("۱۲۳,۴۵۶") == "123456"
    assert normalize_numbers("1,234") == "1234"
