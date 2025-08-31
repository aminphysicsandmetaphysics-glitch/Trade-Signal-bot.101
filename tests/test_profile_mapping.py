from signal_bot import SignalBot


def test_resolve_targets_with_profile_mapping():
    profiles = {
        "default": {
            111: {"dests": [222], "template": "prefix {{ message }}"}
        }
    }
    bot = SignalBot(1, "hash", "session", [111], [333], profiles=profiles)
    dests, template = bot.resolve_targets(111)
    assert dests == [-100222]
    assert template == "prefix {{ message }}"

    dests_default, template_default = bot.resolve_targets(999)
    assert dests_default == [-100333]
    assert template_default is None
