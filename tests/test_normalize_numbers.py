from signal_bot import normalize_numbers


def test_normalize_numbers_removes_commas():
    assert normalize_numbers("۱۲۳,۴۵۶") == "123456"
    assert normalize_numbers("1,234") == "1234"


def test_normalize_numbers_farsi_with_separators():
    assert normalize_numbers("۱٬۲۳۴٬۵۶۷٫۸۹") == "1234567.89"


def test_normalize_numbers_arabic_with_separators():
    assert normalize_numbers("١٬٢٣٤٬٥٦٧٫٨٩") == "1234567.89"
