"""Calculate structure-level bid/offer/mid from individual leg market data."""

from .models import (
    LegMarketData,
    OptionLeg,
    ParsedOrder,
    Side,
    StructureMarketData,
)


def price_structure_from_market(
    order: ParsedOrder,
    leg_market: list[LegMarketData],
    stock_price: float,
) -> StructureMarketData:
    """Calculate structure bid/offer/mid from screen market data.

    For each leg, the contribution to structure bid/offer depends on
    the leg's side (buy/sell):
      - BUY leg: buyer pays the offer, seller receives the bid
      - SELL leg: buyer receives the bid, seller pays the offer

    Structure BID = what the market would pay you for the structure
      = sum of (leg_bid * qty) for SELL legs - sum of (leg_offer * qty) for BUY legs

    Structure OFFER = what it costs to buy the structure from the market
      = sum of (leg_offer * qty) for BUY legs - sum of (leg_bid * qty) for SELL legs

    For structures quoted as net premium (e.g., spreads), the sign convention
    follows the net flow.
    """
    legs = order.structure.legs

    if len(legs) != len(leg_market):
        raise ValueError(
            f"Leg count mismatch: {len(legs)} legs but {len(leg_market)} market entries"
        )

    # Calculate structure bid and offer
    # Bid: the price at which the market bids for the structure
    # Offer: the price at which the market offers the structure
    struct_bid = 0.0
    struct_offer = 0.0

    for leg, mkt in zip(legs, leg_market):
        if leg.side == Side.BUY:
            # Buyer of the structure buys this leg
            # Structure bid: sell to market -> you sell this leg at bid
            struct_bid -= mkt.bid * leg.quantity
            # Structure offer: buy from market -> you buy this leg at offer
            struct_offer -= mkt.offer * leg.quantity
        else:
            # Buyer of the structure sells this leg
            # Structure bid: sell to market -> you buy back at offer
            struct_bid += mkt.offer * leg.quantity
            # Structure offer: buy from market -> you sell at bid
            struct_offer += mkt.bid * leg.quantity

    # Normalize so bid < offer (structure bid is what you receive, offer is what you pay)
    # Convention: positive = net credit, negative = net debit
    # We want bid <= offer in absolute terms
    if struct_bid > struct_offer:
        struct_bid, struct_offer = struct_offer, struct_bid

    # Calculate structure sizes (limited by thinnest leg adjusted for ratio)
    struct_bid_size = _calc_structure_size(legs, leg_market, for_bid=True)
    struct_offer_size = _calc_structure_size(legs, leg_market, for_bid=False)

    return StructureMarketData(
        leg_data=list(zip(legs, leg_market)),
        stock_price=stock_price,
        stock_ref=order.stock_ref,
        delta=order.delta,
        structure_bid=struct_bid,
        structure_offer=struct_offer,
        structure_bid_size=struct_bid_size,
        structure_offer_size=struct_offer_size,
    )


def _calc_structure_size(
    legs: list[OptionLeg],
    leg_market: list[LegMarketData],
    for_bid: bool,
) -> int:
    """Calculate max structure quantity based on screen liquidity.

    Each leg's available size is divided by its quantity-per-structure
    to find how many structures can be filled.
    """
    min_structures = float("inf")
    base_qty = min(leg.quantity for leg in legs) if legs else 1

    for leg, mkt in zip(legs, leg_market):
        if for_bid:
            # To sell the structure: buy legs at offer, sell legs at bid
            available = mkt.bid_size if leg.side == Side.SELL else mkt.offer_size
        else:
            # To buy the structure: buy legs at offer, sell legs at bid
            available = mkt.offer_size if leg.side == Side.BUY else mkt.bid_size

        if leg.quantity > 0:
            structures_possible = available / (leg.quantity / base_qty)
            min_structures = min(min_structures, structures_possible)

    return int(min_structures) if min_structures != float("inf") else 0
