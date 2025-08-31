from signal_bot import guess_position


def test_guess_position_buy_synonym():
    assert guess_position("We should grab long on gold") == "Buy"


def test_guess_position_sell_synonym():
    assert guess_position("Time to offload some positions") == "Sell"
