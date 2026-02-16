"""Tests for the IDB broker shorthand parser."""

from datetime import date

import pytest

from options_pricer.models import OptionType, Side, QuoteSide
from options_pricer.parser import (
    parse_order,
    _extract_stock_ref,
    _extract_delta,
    _extract_quantity,
    _extract_price_and_side,
    _extract_ratio,
    _extract_modifier,
    _extract_structure_type,
)


class TestExtractStockRef:
    def test_vs_no_space(self):
        assert _extract_stock_ref("AAPL Jun26 300 calls vs250.32") == 250.32

    def test_vs_space(self):
        assert _extract_stock_ref("vs 262.54") == 262.54

    def test_vs_dot(self):
        assert _extract_stock_ref("vs. 250") == 250.0

    def test_tt_no_space(self):
        assert _extract_stock_ref("tt69.86") == 69.86

    def test_tt_space(self):
        assert _extract_stock_ref("tt 171.10") == 171.10

    def test_t_space(self):
        assert _extract_stock_ref("AAPL t 250.00") == 250.00

    def test_none(self):
        assert _extract_stock_ref("AAPL Jun26 300 calls") is None


class TestExtractDelta:
    def test_simple(self):
        assert _extract_delta("30d") == 30.0

    def test_single_digit(self):
        assert _extract_delta("3d") == 3.0

    def test_on_a(self):
        assert _extract_delta("on a 11d") == 11.0

    def test_in_context(self):
        assert _extract_delta("UBER Jun26 45P tt69.86 3d 0.41 bid") == 3.0


class TestExtractQuantity:
    def test_simple(self):
        assert _extract_quantity("1058x") == 1058

    def test_in_context(self):
        assert _extract_quantity("AAPL Jun26 300 calls 500x") == 500

    def test_with_ratio(self):
        # Should not match the "1" in "1X2", should match "500x"
        assert _extract_quantity("PS 1X2 500x") == 500

    def test_k_format_simple(self):
        assert _extract_quantity("1k") == 1000

    def test_k_format_larger(self):
        assert _extract_quantity("2k") == 2000

    def test_k_format_in_context(self):
        assert _extract_quantity("goog jun 100 90 ps vs 200.00 10d 1 bid 1k") == 1000


class TestExtractPriceAndSide:
    def test_bid_word(self):
        price, side = _extract_price_and_side("20.50 bid")
        assert price == 20.50
        assert side == QuoteSide.BID

    def test_bid_suffix(self):
        price, side = _extract_price_and_side("2.4b")
        assert price == 2.4
        assert side == QuoteSide.BID

    def test_at_symbol(self):
        price, side = _extract_price_and_side("@ 1.60")
        assert price == 1.60
        assert side == QuoteSide.OFFER

    def test_at_with_qty(self):
        price, side = _extract_price_and_side("500 @ 2.55")
        assert price == 2.55
        assert side == QuoteSide.OFFER

    def test_offer_word(self):
        price, side = _extract_price_and_side("5.00 offer")
        assert price == 5.00
        assert side == QuoteSide.OFFER


class TestExtractRatio:
    def test_1x2(self):
        assert _extract_ratio("PS 1X2 500x") == (1, 2)

    def test_1x3(self):
        assert _extract_ratio("1x3") == (1, 3)

    def test_no_ratio(self):
        assert _extract_ratio("500x @ 3.50") is None


class TestExtractModifier:
    def test_putover(self):
        assert _extract_modifier("putover") == "putover"

    def test_put_over(self):
        assert _extract_modifier("put over") == "putover"

    def test_callover(self):
        assert _extract_modifier("callover") == "callover"

    def test_nx_over(self):
        assert _extract_modifier("1X over") == "1x_over"


class TestExtractStructureType:
    def test_ps(self):
        assert _extract_structure_type("AAPL Jun26 240/220 PS") == "put_spread"

    def test_cs(self):
        assert _extract_structure_type("AAPL Jun26 240/280 CS") == "call_spread"

    def test_risky(self):
        assert _extract_structure_type("IWM feb 257 apr 280 Risky") == "risk_reversal"

    def test_straddle(self):
        assert _extract_structure_type("AAPL Jun26 250 straddle") == "straddle"

    def test_fly(self):
        assert _extract_structure_type("AAPL fly 240/250/260") == "butterfly"


class TestParseOrder:
    def test_single_call(self):
        order = parse_order("AAPL jun26 300 calls vs250.32 30d 20.50 bid 1058x")
        assert order.underlying == "AAPL"
        assert order.stock_ref == 250.32
        assert order.delta == 30.0
        assert order.price == 20.50
        assert order.quote_side == QuoteSide.BID
        assert order.quantity == 1058
        assert len(order.structure.legs) == 1
        leg = order.structure.legs[0]
        assert leg.strike == 300.0
        assert leg.option_type == OptionType.CALL
        assert leg.expiry == date(2026, 6, 16)

    def test_single_put_with_tt(self):
        order = parse_order("UBER Jun26 45P tt69.86 3d 0.41 bid 1058x")
        assert order.underlying == "UBER"
        assert order.stock_ref == 69.86
        assert order.delta == 3.0
        assert order.price == 0.41
        assert order.quote_side == QuoteSide.BID
        assert len(order.structure.legs) == 1
        leg = order.structure.legs[0]
        assert leg.strike == 45.0
        assert leg.option_type == OptionType.PUT

    def test_put_strike_before_expiry(self):
        order = parse_order("QCOM 85P Jan27 tt141.17 7d 2.4b 600x")
        assert order.underlying == "QCOM"
        assert order.stock_ref == 141.17
        assert order.delta == 7.0
        assert order.price == 2.4
        assert order.quote_side == QuoteSide.BID
        assert order.quantity == 600
        leg = order.structure.legs[0]
        assert leg.strike == 85.0
        assert leg.option_type == OptionType.PUT
        assert leg.expiry == date(2027, 1, 16)

    def test_at_price_convention(self):
        order = parse_order("VST Apr 130p 500 @ 2.55 tt 171.10 on a 11d")
        assert order.underlying == "VST"
        assert order.stock_ref == 171.10
        assert order.delta == 11.0
        assert order.price == 2.55
        assert order.quote_side == QuoteSide.OFFER
        leg = order.structure.legs[0]
        assert leg.strike == 130.0
        assert leg.option_type == OptionType.PUT

    def test_calendar_risk_reversal(self):
        order = parse_order(
            "IWM feb 257 apr 280 Risky vs 262.54 52d 2500x @ 1.60"
        )
        assert order.underlying == "IWM"
        assert order.stock_ref == 262.54
        assert order.delta == 52.0
        assert order.price == 1.60
        assert order.quantity == 2500
        assert len(order.structure.legs) == 2
        # Lower strike should be the put, higher the call
        put_leg = [l for l in order.structure.legs
                   if l.option_type == OptionType.PUT][0]
        call_leg = [l for l in order.structure.legs
                    if l.option_type == OptionType.CALL][0]
        assert put_leg.strike == 257.0
        assert call_leg.strike == 280.0

    def test_put_spread_ratio(self):
        order = parse_order(
            "AAPL Jun26 240/220 PS 1X2 vs250 15d 500x @ 3.50 1X over"
        )
        assert order.underlying == "AAPL"
        assert order.stock_ref == 250.0
        assert order.delta == 15.0
        assert order.price == 3.50
        assert len(order.structure.legs) == 2
        # Sell higher strike (240P), buy lower strike (220P) at 2x
        sell_leg = [l for l in order.structure.legs if l.side == Side.SELL][0]
        buy_leg = [l for l in order.structure.legs if l.side == Side.BUY][0]
        assert sell_leg.strike == 240.0
        assert sell_leg.option_type == OptionType.PUT
        assert sell_leg.quantity == 500  # 500 * r1(1)
        assert buy_leg.strike == 220.0
        assert buy_leg.option_type == OptionType.PUT
        assert buy_leg.quantity == 1000  # 500 * r2(2)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_order("")

    def test_ticker_uppercased(self):
        order = parse_order("aapl Jun26 300 calls vs250 30d 5.00 bid 100x")
        assert order.underlying == "AAPL"
