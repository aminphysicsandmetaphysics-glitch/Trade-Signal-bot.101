import pytest
from signal_bot import parse_signal


def test_parse_signal_rejects_buy_sl_not_below_entry():
    message = (
        "#XAUUSD\nBuy\nEntry Price : 1900\nTP1 : 1905\nTP2 : 1910\nStop Loss : 1901\n"
    )
    assert parse_signal(message, 1234, {}) is None


def test_parse_signal_rejects_sell_sl_not_above_entry():
    message = (
        "#XAUUSD\nSell\nEntry Price : 1900\nTP1 : 1895\nTP2 : 1890\nStop Loss : 1899\n"
    )
    assert parse_signal(message, 1234, {}) is None


def test_parse_signal_rejects_buy_all_tp_below_entry():
    message = (
        "#XAUUSD\nBuy\nEntry Price : 1900\nTP1 : 1890\nTP2 : 1895\nStop Loss : 1880\n"
    )
    assert parse_signal(message, 1234, {}) is None


def test_parse_signal_rejects_sell_all_tp_above_entry():
    message = (
        "#XAUUSD\nSell\nEntry Price : 1900\nTP1 : 1910\nTP2 : 1920\nStop Loss : 1925\n"
    )
    assert parse_signal(message, 1234, {}) is None


def test_parse_signal_entry_range_invalid_tp():
    profile = {"allow_entry_range": True}
    message = (
        "#XAUUSD\nBuy\nEntry: @1900-1910\nTP1: 1905\nTP2: 1908\nSL: 1890\n"
    )
    assert parse_signal(message, 1234, profile) is None


def test_parse_signal_entry_range_invalid_sl():
    profile = {"allow_entry_range": True}
    message = (
        "#XAUUSD\nSell\nEntry: @1930-1935\nTP1: 1920\nTP2: 1910\nSL: 1925\n"
    )
    assert parse_signal(message, 1234, profile) is None


def test_parse_signal_rejects_buy_tp_equal_entry():
    message = (
        "#XAUUSD\nBuy\nEntry Price : 1900\nTP1 : 1900\nTP2 : 1910\nStop Loss : 1890\n"
    )
    assert parse_signal(message, 1234, {}) is None


def test_parse_signal_rejects_sell_tp_equal_entry():
    message = (
        "#XAUUSD\nSell\nEntry Price : 1900\nTP1 : 1900\nTP2 : 1890\nStop Loss : 1910\n"
    )
    assert parse_signal(message, 1234, {}) is None


def test_parse_signal_rejects_buy_sl_equal_entry():
    message = (
        "#XAUUSD\nBuy\nEntry Price : 1900\nTP1 : 1905\nTP2 : 1910\nStop Loss : 1900\n"
    )
    assert parse_signal(message, 1234, {}) is None


def test_parse_signal_rejects_sell_sl_equal_entry():
    message = (
        "#XAUUSD\nSell\nEntry Price : 1900\nTP1 : 1895\nTP2 : 1890\nStop Loss : 1900\n"
    )
    assert parse_signal(message, 1234, {}) is None
