"""Tests for structure-level bid/offer/mid pricing from screen market data."""

from datetime import date

import pytest

from options_pricer.models import (
    LegMarketData,
    OptionLeg,
    OptionStructure,
    OptionType,
    ParsedOrder,
    QuoteSide,
    Side,
)
from options_pricer.structure_pricer import price_structure_from_market


def _make_order(legs, stock_ref=250.0, delta=30.0, quantity=1):
    """Helper to create a ParsedOrder from legs."""
    return ParsedOrder(
        underlying="TEST",
        structure=OptionStructure(name="test", legs=legs),
        stock_ref=stock_ref,
        delta=delta,
        price=0.0,
        quote_side=QuoteSide.BID,
        quantity=quantity,
        raw_text="test",
    )


def _make_leg(strike, option_type, side, qty=1, expiry=None):
    return OptionLeg(
        underlying="TEST",
        expiry=expiry or date(2026, 6, 19),
        strike=strike,
        option_type=option_type,
        side=side,
        quantity=qty,
    )


class TestStructurePricing:
    """Test structure bid/offer/mid calculations."""

    def test_single_buy_call(self):
        """Single buy call: bid = what you sell for, offer = what you buy for."""
        leg = _make_leg(300, OptionType.CALL, Side.BUY)
        mkt = LegMarketData(bid=5.00, bid_size=100, offer=5.50, offer_size=200)
        order = _make_order([leg])

        result = price_structure_from_market(order, [mkt], stock_price=250.0)

        # Mid should always be correct
        assert abs(result.structure_mid) == pytest.approx(5.25, abs=0.01)

    def test_single_sell_put(self):
        """Single sell put: you receive bid when selling."""
        leg = _make_leg(240, OptionType.PUT, Side.SELL)
        mkt = LegMarketData(bid=3.00, bid_size=150, offer=3.50, offer_size=100)
        order = _make_order([leg])

        result = price_structure_from_market(order, [mkt], stock_price=250.0)

        assert abs(result.structure_mid) == pytest.approx(3.25, abs=0.01)

    def test_put_spread(self):
        """Put spread (buy higher strike, sell lower): debit spread."""
        buy_leg = _make_leg(240, OptionType.PUT, Side.BUY)
        sell_leg = _make_leg(220, OptionType.PUT, Side.SELL)
        mkt_buy = LegMarketData(bid=10.00, bid_size=100, offer=10.50, offer_size=100)
        mkt_sell = LegMarketData(bid=3.00, bid_size=100, offer=3.50, offer_size=100)
        order = _make_order([buy_leg, sell_leg])

        result = price_structure_from_market(order, [mkt_buy, mkt_sell], stock_price=250.0)

        # Mid = (10.25 - 3.25) = 7.00
        assert abs(result.structure_mid) == pytest.approx(7.00, abs=0.01)

    def test_straddle(self):
        """Straddle: buy call + buy put at same strike."""
        call = _make_leg(250, OptionType.CALL, Side.BUY)
        put = _make_leg(250, OptionType.PUT, Side.BUY)
        mkt_c = LegMarketData(bid=8.00, bid_size=50, offer=8.50, offer_size=50)
        mkt_p = LegMarketData(bid=7.00, bid_size=60, offer=7.50, offer_size=60)
        order = _make_order([call, put])

        result = price_structure_from_market(order, [mkt_c, mkt_p], stock_price=250.0)

        # Mid = 8.25 + 7.25 = 15.50
        assert abs(result.structure_mid) == pytest.approx(15.50, abs=0.01)

    def test_risk_reversal(self):
        """Risk reversal: sell put, buy call."""
        sell_put = _make_leg(240, OptionType.PUT, Side.SELL)
        buy_call = _make_leg(260, OptionType.CALL, Side.BUY)
        mkt_p = LegMarketData(bid=5.00, bid_size=100, offer=5.50, offer_size=100)
        mkt_c = LegMarketData(bid=4.00, bid_size=100, offer=4.50, offer_size=100)
        order = _make_order([sell_put, buy_call])

        result = price_structure_from_market(order, [mkt_p, mkt_c], stock_price=250.0)

        # Mid: receive 5.25 for put, pay 4.25 for call = net credit 1.00
        assert abs(result.structure_mid) == pytest.approx(1.00, abs=0.01)

    def test_bid_leq_offer(self):
        """Verify structure bid <= offer after normalization."""
        leg = _make_leg(300, OptionType.CALL, Side.BUY)
        mkt = LegMarketData(bid=5.00, bid_size=100, offer=5.50, offer_size=200)
        order = _make_order([leg])

        result = price_structure_from_market(order, [mkt], stock_price=250.0)

        assert result.structure_bid <= result.structure_offer

    def test_spread_bid_leq_offer(self):
        """Spread bid <= offer after normalization."""
        buy_leg = _make_leg(300, OptionType.CALL, Side.BUY)
        sell_leg = _make_leg(310, OptionType.CALL, Side.SELL)
        mkt_buy = LegMarketData(bid=5.00, bid_size=100, offer=5.50, offer_size=100)
        mkt_sell = LegMarketData(bid=2.00, bid_size=100, offer=2.50, offer_size=100)
        order = _make_order([buy_leg, sell_leg])

        result = price_structure_from_market(order, [mkt_buy, mkt_sell], stock_price=250.0)

        assert result.structure_bid <= result.structure_offer

    def test_ratio_spread(self):
        """1x2 put spread: sell 1 higher strike, buy 2 lower strike."""
        sell_leg = _make_leg(240, OptionType.PUT, Side.SELL, qty=1)
        buy_leg = _make_leg(220, OptionType.PUT, Side.BUY, qty=2)
        mkt_sell = LegMarketData(bid=10.00, bid_size=100, offer=10.50, offer_size=100)
        mkt_buy = LegMarketData(bid=3.00, bid_size=200, offer=3.50, offer_size=200)
        order = _make_order([sell_leg, buy_leg])

        result = price_structure_from_market(order, [mkt_sell, mkt_buy], stock_price=250.0)

        # Mid: receive 10.25*1 for sell, pay 3.25*2 for buys = 10.25 - 6.50 = 3.75
        assert abs(result.structure_mid) == pytest.approx(3.75, abs=0.01)

    def test_leg_count_mismatch_raises(self):
        """Mismatched leg/market counts should raise ValueError."""
        leg = _make_leg(300, OptionType.CALL, Side.BUY)
        order = _make_order([leg])

        with pytest.raises(ValueError, match="Leg count mismatch"):
            price_structure_from_market(order, [], stock_price=250.0)


class TestStructureSize:
    """Test structure size (liquidity) calculations."""

    def test_single_leg_size(self):
        """Single leg: structure size equals leg size."""
        leg = _make_leg(300, OptionType.CALL, Side.BUY)
        mkt = LegMarketData(bid=5.00, bid_size=100, offer=5.50, offer_size=200)
        order = _make_order([leg])

        result = price_structure_from_market(order, [mkt], stock_price=250.0)

        # Offer size for buying a single BUY leg
        assert result.structure_offer_size == 200

    def test_spread_size_limited_by_thinnest(self):
        """Spread size limited by thinnest leg."""
        buy_leg = _make_leg(240, OptionType.PUT, Side.BUY)
        sell_leg = _make_leg(220, OptionType.PUT, Side.SELL)
        mkt_buy = LegMarketData(bid=10.00, bid_size=500, offer=10.50, offer_size=300)
        mkt_sell = LegMarketData(bid=3.00, bid_size=100, offer=3.50, offer_size=200)
        order = _make_order([buy_leg, sell_leg])

        result = price_structure_from_market(order, [mkt_buy, mkt_sell], stock_price=250.0)

        # To buy the structure: buy at offer (300 available), sell at bid (100 available)
        # Limited by the sell_leg bid_size = 100
        assert result.structure_offer_size == min(300, 100)
