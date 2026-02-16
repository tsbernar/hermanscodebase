"""Bloomberg API wrapper for live market data.

Provides a mock-friendly interface so the dashboard and tests can run
without a Bloomberg Terminal connection.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date

from scipy.stats import norm

from .settings import BLOOMBERG_HOST, BLOOMBERG_PORT, DEFAULT_RISK_FREE_RATE

logger = logging.getLogger(__name__)


@dataclass
class MarketData:
    """Snapshot of market data for an underlying."""

    underlying: str
    spot: float
    implied_vols: dict[tuple[date, float], float] = field(default_factory=dict)
    risk_free_rate: float = 0.05
    dividend_yield: float = 0.0


@dataclass
class OptionQuote:
    """Bid/offer quote for a single option from screen."""

    bid: float = 0.0
    bid_size: int = 0
    offer: float = 0.0
    offer_size: int = 0


class BloombergClient:
    """Wrapper around blpapi for fetching live market data."""

    def __init__(self, host: str = BLOOMBERG_HOST, port: int = BLOOMBERG_PORT):
        self._host = host
        self._port = port
        self._session = None

    def connect(self) -> bool:
        try:
            import blpapi

            session_options = blpapi.SessionOptions()
            session_options.setServerHost(self._host)
            session_options.setServerPort(self._port)
            self._session = blpapi.Session(session_options)
            return self._session.start()
        except ImportError:
            logger.info("blpapi not installed — Bloomberg connection unavailable")
            return False
        except Exception:
            logger.warning("Failed to connect to Bloomberg Terminal", exc_info=True)
            return False

    def disconnect(self):
        if self._session:
            self._session.stop()
            self._session = None

    def get_spot(self, underlying: str) -> float | None:
        if not self._session:
            return None
        try:
            import blpapi

            refdata = self._session.getService("//blp/refdata")
            request = refdata.createRequest("ReferenceDataRequest")
            request.append("securities", f"{underlying} US Equity")
            request.append("fields", "PX_LAST")
            self._session.sendRequest(request)

            while True:
                event = self._session.nextEvent(500)
                for msg in event:
                    if msg.hasElement("securityData"):
                        sec_data = msg.getElement("securityData").getValueAsElement(0)
                        field_data = sec_data.getElement("fieldData")
                        return field_data.getElementAsFloat("PX_LAST")
                if event.eventType() == blpapi.Event.RESPONSE:
                    break
        except Exception:
            logger.warning("Failed to fetch spot for %s", underlying, exc_info=True)
            return None

    def get_option_quote(
        self, underlying: str, expiry: date, strike: float, option_type: str,
    ) -> OptionQuote:
        """Fetch live bid/offer/size for a specific option from Bloomberg."""
        if not self._session:
            return OptionQuote()
        try:
            import blpapi

            # Build Bloomberg option ticker
            # Format: "AAPL 06/16/26 C300 Equity" for AAPL Jun26 300 Call
            exp_str = expiry.strftime("%m/%d/%y")
            type_char = "C" if option_type == "call" else "P"
            ticker = f"{underlying} {exp_str} {type_char}{strike:.0f} Equity"

            refdata = self._session.getService("//blp/refdata")
            request = refdata.createRequest("ReferenceDataRequest")
            request.append("securities", ticker)
            request.append("fields", "BID")
            request.append("fields", "ASK")
            request.append("fields", "BID_SIZE")
            request.append("fields", "ASK_SIZE")
            self._session.sendRequest(request)

            quote = OptionQuote()
            while True:
                event = self._session.nextEvent(500)
                for msg in event:
                    if msg.hasElement("securityData"):
                        sec_data = msg.getElement("securityData").getValueAsElement(0)
                        fd = sec_data.getElement("fieldData")
                        try:
                            quote.bid = fd.getElementAsFloat("BID")
                        except Exception:
                            logger.debug("BID field missing for %s", ticker)
                        try:
                            quote.offer = fd.getElementAsFloat("ASK")
                        except Exception:
                            logger.debug("ASK field missing for %s", ticker)
                        try:
                            quote.bid_size = int(fd.getElementAsFloat("BID_SIZE"))
                        except Exception:
                            logger.debug("BID_SIZE field missing for %s", ticker)
                        try:
                            quote.offer_size = int(fd.getElementAsFloat("ASK_SIZE"))
                        except Exception:
                            logger.debug("ASK_SIZE field missing for %s", ticker)
                if event.eventType() == blpapi.Event.RESPONSE:
                    break
            return quote
        except Exception:
            logger.warning("Failed to fetch option quote for %s", underlying, exc_info=True)
            return OptionQuote()

    def get_implied_vol(
        self, underlying: str, expiry: date, strike: float,
    ) -> float | None:
        if not self._session:
            return None
        return None

    def get_risk_free_rate(self) -> float:
        if not self._session:
            return DEFAULT_RISK_FREE_RATE
        return DEFAULT_RISK_FREE_RATE

    def get_contract_multiplier(self, underlying: str) -> int:
        """Fetch OPT_CONT_SIZE from Bloomberg for the underlying's options."""
        if not self._session:
            return 100
        try:
            import blpapi

            refdata = self._session.getService("//blp/refdata")
            request = refdata.createRequest("ReferenceDataRequest")
            request.append("securities", f"{underlying} US Equity")
            request.append("fields", "OPT_CONT_SIZE")
            self._session.sendRequest(request)

            while True:
                event = self._session.nextEvent(500)
                for msg in event:
                    if msg.hasElement("securityData"):
                        sec_data = msg.getElement("securityData").getValueAsElement(0)
                        field_data = sec_data.getElement("fieldData")
                        return int(field_data.getElementAsFloat("OPT_CONT_SIZE"))
                if event.eventType() == blpapi.Event.RESPONSE:
                    break
        except Exception:
            logger.warning("Failed to fetch contract multiplier for %s, defaulting to 100",
                           underlying, exc_info=True)
        return 100

    def get_market_data(self, underlying: str) -> MarketData:
        spot = self.get_spot(underlying)
        rate = self.get_risk_free_rate()
        return MarketData(
            underlying=underlying,
            spot=spot or 0.0,
            risk_free_rate=rate,
        )


class MockBloombergClient:
    """Mock Bloomberg client with realistic option pricing for development.

    Uses Black-Scholes pricing with a vol skew surface to generate
    realistic bid/offer quotes for development without a Bloomberg Terminal.
    """

    _MOCK_SPOTS: dict[str, float] = {
        "AAPL": 250.30,
        "MSFT": 415.20,
        "GOOGL": 175.80,
        "AMZN": 195.60,
        "TSLA": 245.30,
        "SPY": 520.40,
        "QQQ": 445.10,
        "META": 560.75,
        "NVDA": 880.50,
        "IWM": 262.60,
        "UBER": 69.90,
        "QCOM": 141.20,
        "VST": 171.10,
        "SPX": 5204.00,
        "NFLX": 950.00,
    }

    _MOCK_VOLS: dict[str, float] = {
        "AAPL": 0.22,
        "MSFT": 0.20,
        "GOOGL": 0.25,
        "AMZN": 0.28,
        "TSLA": 0.45,
        "SPY": 0.14,
        "QQQ": 0.18,
        "META": 0.32,
        "NVDA": 0.42,
        "IWM": 0.18,
        "UBER": 0.35,
        "QCOM": 0.30,
        "VST": 0.38,
        "SPX": 0.14,
        "NFLX": 0.34,
    }

    def connect(self) -> bool:
        return True

    def disconnect(self):
        pass

    def get_spot(self, underlying: str) -> float:
        return self._MOCK_SPOTS.get(underlying.upper(), 100.0)

    def get_option_quote(
        self, underlying: str, expiry: date, strike: float, option_type: str,
    ) -> OptionQuote:
        """Generate realistic option quotes using Black-Scholes with a spread."""
        spot = self.get_spot(underlying)
        vol = self._get_vol(underlying, strike, spot)
        rate = DEFAULT_RISK_FREE_RATE

        today = date.today()
        T = max((expiry - today).days / 365.0, 0.001)

        # Calculate theoretical price via Black-Scholes
        theo = self._bs_price(spot, strike, T, rate, vol, option_type)

        # Add realistic bid-ask spread (wider for further OTM)
        moneyness = abs(spot - strike) / spot
        spread_pct = 0.02 + 0.03 * moneyness  # 2-5% spread
        half_spread = max(theo * spread_pct, 0.05)

        bid = max(theo - half_spread, 0.01)
        offer = theo + half_spread

        # Generate realistic sizes
        import random
        random.seed(int(strike * 100 + spot * 10))
        bid_size = random.randint(100, 1000)
        offer_size = random.randint(100, 800)

        return OptionQuote(
            bid=round(bid, 2),
            bid_size=bid_size,
            offer=round(offer, 2),
            offer_size=offer_size,
        )

    def get_implied_vol(
        self, underlying: str, expiry: date, strike: float,
    ) -> float:
        spot = self.get_spot(underlying)
        return self._get_vol(underlying, strike, spot)

    def get_risk_free_rate(self) -> float:
        return DEFAULT_RISK_FREE_RATE

    def get_contract_multiplier(self, underlying: str) -> int:
        """Return contract multiplier. 100 for equity options."""
        return 100

    def get_market_data(self, underlying: str) -> MarketData:
        return MarketData(
            underlying=underlying,
            spot=self.get_spot(underlying),
            risk_free_rate=self.get_risk_free_rate(),
        )

    def _get_vol(self, underlying: str, strike: float, spot: float) -> float:
        base_vol = self._MOCK_VOLS.get(underlying.upper(), 0.25)
        moneyness = strike / spot
        # Vol skew: OTM puts have higher vol
        skew = 0.05 * (1.0 - moneyness) if moneyness < 1.0 else 0.0
        return base_vol + skew

    @staticmethod
    def _bs_price(
        S: float, K: float, T: float, r: float, sigma: float, option_type: str,
        q: float = 0.0,
    ) -> float:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        if option_type == "call":
            return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        else:
            return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)


def create_client(use_mock: bool = False, **kwargs) -> BloombergClient | MockBloombergClient:
    """Factory to create a Bloomberg client, falling back to mock if needed."""
    if use_mock:
        return MockBloombergClient()
    client = BloombergClient(**kwargs)
    if client.connect():
        return client
    return MockBloombergClient()
