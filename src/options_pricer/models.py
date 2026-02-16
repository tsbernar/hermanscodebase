"""Data models for IDB option orders and structures."""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class OptionType(Enum):
    CALL = "call"
    PUT = "put"


class Side(Enum):
    BUY = "buy"
    SELL = "sell"


class QuoteSide(Enum):
    BID = "bid"
    OFFER = "offer"


@dataclass
class OptionLeg:
    """A single option leg within a structure."""

    underlying: str
    expiry: date
    strike: float
    option_type: OptionType
    side: Side
    quantity: int = 1
    ratio: int = 1

    @property
    def direction(self) -> int:
        """Return +1 for buy, -1 for sell."""
        return 1 if self.side == Side.BUY else -1

    def payoff(self, spot: float) -> float:
        """Calculate per-unit payoff at expiration for a given spot price."""
        if self.option_type == OptionType.CALL:
            intrinsic = max(spot - self.strike, 0.0)
        else:
            intrinsic = max(self.strike - spot, 0.0)
        return self.direction * self.quantity * intrinsic


@dataclass
class OptionStructure:
    """A multi-leg option structure (spread, straddle, etc.)."""

    name: str
    legs: list[OptionLeg] = field(default_factory=list)
    description: str = ""

    def total_payoff(self, spot: float) -> float:
        """Calculate total structure payoff at a given spot price."""
        return sum(leg.payoff(spot) for leg in self.legs)

    def payoff_range(
        self, spot_low: float, spot_high: float, steps: int = 200
    ) -> list[tuple[float, float]]:
        """Calculate payoff across a range of spot prices."""
        step_size = (spot_high - spot_low) / steps
        return [
            (spot_low + i * step_size, self.total_payoff(spot_low + i * step_size))
            for i in range(steps + 1)
        ]

    @property
    def net_quantity(self) -> int:
        return sum(leg.direction * leg.quantity for leg in self.legs)

    @property
    def underlyings(self) -> set[str]:
        return {leg.underlying for leg in self.legs}


@dataclass
class ParsedOrder:
    """A fully parsed IDB broker order with all metadata."""

    underlying: str
    structure: OptionStructure
    stock_ref: float
    delta: float
    price: float
    quote_side: QuoteSide
    quantity: int
    raw_text: str = ""


@dataclass
class LegMarketData:
    """Market data for a single option leg from screen."""

    bid: float = 0.0
    bid_size: int = 0
    offer: float = 0.0
    offer_size: int = 0

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.offer > 0:
            return (self.bid + self.offer) / 2.0
        return self.bid or self.offer


@dataclass
class StructureMarketData:
    """Full market pricing for a structure."""

    leg_data: list[tuple[OptionLeg, LegMarketData]] = field(default_factory=list)
    stock_price: float = 0.0
    stock_ref: float = 0.0
    delta: float = 0.0
    structure_bid: float = 0.0
    structure_offer: float = 0.0
    structure_bid_size: int = 0
    structure_offer_size: int = 0

    @property
    def structure_mid(self) -> float:
        return (self.structure_bid + self.structure_offer) / 2.0
