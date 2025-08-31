from signal_bot import classic_extract_tps


def test_classic_extract_tps_mixed_content():
    lines = [
        "TP1 1.2345, TP2 1.3456",
        "Target 1.4000 / 1.5000 and 50 pips",
        "Random line 1.0000",
        "TP3: 1.4567 80 pips 1.5678",
        "TP4: 1.6000 30 pts 1.7000",
        "TP5: 1.8000 1% 1.9000",
    ]
    assert classic_extract_tps(lines) == [
        "1.2345",
        "1.3456",
        "1.4000",
        "1.5000",
        "1.4567",
        "1.5678",
        "1.6000",
        "1.7000",
        "1.8000",
        "1.9000",
    ]
