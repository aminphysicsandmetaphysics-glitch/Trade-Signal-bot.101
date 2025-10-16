from signal_bot.parsers.parse_signal_2xclub import parse_signal_2xclub


def test_reject_non_signal():
    assert parse_signal_2xclub("سلام وقت بخیر") is None


def test_detect_update_message():
    msg = """✅+12.5%
استاپ بیاد نقطه ورود"""
    parsed = parse_signal_2xclub(msg)
    assert parsed == {"is_update": True}

def test_long_two_entries():
    msg = """📈رمزارز  FORM
با لوریج 2 و در نقاط 0.8571 و 0.816 پوزیشن لانگ باز کنید.
🎯تارگت:
0.9073 - 0.9844 - 1.0825 - 1.1968
❌استاپ:
0.7572
"""
    p = parse_signal_2xclub(msg)
    assert not p["is_update"]
    assert p["symbol"] == "FORMUSDT"
    assert p["side"] == "LONG"
    assert p["leverage"] == 2
    assert abs(p["entry"] - 0.816) < 1e-9
    assert p["targets"][0] == 0.9073
    assert p["stop"] == 0.7572
    assert p["rr"].startswith("1/")


def test_short_signal_pick_highest_entry():
    msg = """#BTC/USDT
پوزیشن شورت باز کنید
در نقطه 27461.5
تارگت: 26000
استاپ: 28000"""
    parsed = parse_signal_2xclub(msg)
    assert not parsed["is_update"]
    assert parsed["side"] == "SHORT"
    assert abs(parsed["entry"] - 27461.5) < 1e-9
