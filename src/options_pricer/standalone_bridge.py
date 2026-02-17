#!/usr/bin/env python3
"""Bloomberg Bridge — standalone HTTP server for browser-based market data access.

Save this file on your Bloomberg desktop and run:
    python bloomberg_bridge.py

Connects to Bloomberg Terminal via blpapi on port 8194.
Falls back to mock data if Bloomberg is not available.
Dashboard auto-detects the bridge at http://127.0.0.1:8195

Requirements installed automatically on first run:
    flask, flask-cors
Optional (for live Bloomberg data):
    blpapi
"""

# ---------------------------------------------------------------------------
# Auto-install dependencies
# ---------------------------------------------------------------------------
import subprocess, sys

def _ensure_installed(*packages):
    missing = []
    for pkg in packages:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Installing: {', '.join(missing)}...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing
        )

_ensure_installed("flask", "flask-cors")

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
import argparse
import logging
import math
import random
from dataclasses import dataclass
from datetime import date, datetime

from flask import Flask, jsonify, request
from flask_cors import CORS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BRIDGE_PORT = 8195
BLOOMBERG_HOST = "localhost"
BLOOMBERG_PORT = 8194
RISK_FREE_RATE = 0.05

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class OptionQuote:
    bid: float = 0.0
    bid_size: int = 0
    offer: float = 0.0
    offer_size: int = 0

# ---------------------------------------------------------------------------
# Bloomberg client (live)
# ---------------------------------------------------------------------------

class BloombergClient:
    def __init__(self, host=BLOOMBERG_HOST, port=BLOOMBERG_PORT):
        self._host = host
        self._port = port
        self._session = None

    def connect(self):
        try:
            import blpapi
            opts = blpapi.SessionOptions()
            opts.setServerHost(self._host)
            opts.setServerPort(self._port)
            self._session = blpapi.Session(opts)
            return self._session.start()
        except ImportError:
            logger.info("blpapi not installed")
            return False
        except Exception:
            logger.warning("Bloomberg connection failed", exc_info=True)
            return False

    def get_spot(self, underlying):
        if not self._session:
            return None
        try:
            import blpapi
            refdata = self._session.getService("//blp/refdata")
            req = refdata.createRequest("ReferenceDataRequest")
            req.append("securities", f"{underlying} US Equity")
            req.append("fields", "PX_LAST")
            self._session.sendRequest(req)
            while True:
                ev = self._session.nextEvent(500)
                for msg in ev:
                    if msg.hasElement("securityData"):
                        sd = msg.getElement("securityData").getValueAsElement(0)
                        return sd.getElement("fieldData").getElementAsFloat("PX_LAST")
                if ev.eventType() == blpapi.Event.RESPONSE:
                    break
        except Exception:
            logger.warning("Failed to fetch spot for %s", underlying)
        return None

    def get_option_quote(self, underlying, expiry, strike, option_type):
        if not self._session:
            return OptionQuote()
        try:
            import blpapi
            exp_str = expiry.strftime("%m/%d/%y")
            type_char = "C" if option_type == "call" else "P"
            ticker = f"{underlying} {exp_str} {type_char}{strike:.0f} Equity"
            refdata = self._session.getService("//blp/refdata")
            req = refdata.createRequest("ReferenceDataRequest")
            req.append("securities", ticker)
            for f in ("BID", "ASK", "BID_SIZE", "ASK_SIZE"):
                req.append("fields", f)
            self._session.sendRequest(req)
            q = OptionQuote()
            while True:
                ev = self._session.nextEvent(500)
                for msg in ev:
                    if msg.hasElement("securityData"):
                        fd = msg.getElement("securityData").getValueAsElement(0).getElement("fieldData")
                        try: q.bid = fd.getElementAsFloat("BID")
                        except Exception: pass
                        try: q.offer = fd.getElementAsFloat("ASK")
                        except Exception: pass
                        try: q.bid_size = int(fd.getElementAsFloat("BID_SIZE"))
                        except Exception: pass
                        try: q.offer_size = int(fd.getElementAsFloat("ASK_SIZE"))
                        except Exception: pass
                if ev.eventType() == blpapi.Event.RESPONSE:
                    break
            return q
        except Exception:
            logger.warning("Failed to fetch option quote for %s", underlying)
            return OptionQuote()

    def get_contract_multiplier(self, underlying):
        if not self._session:
            return 100
        try:
            import blpapi
            refdata = self._session.getService("//blp/refdata")
            req = refdata.createRequest("ReferenceDataRequest")
            req.append("securities", f"{underlying} US Equity")
            req.append("fields", "OPT_CONT_SIZE")
            self._session.sendRequest(req)
            while True:
                ev = self._session.nextEvent(500)
                for msg in ev:
                    if msg.hasElement("securityData"):
                        fd = msg.getElement("securityData").getValueAsElement(0).getElement("fieldData")
                        return int(fd.getElementAsFloat("OPT_CONT_SIZE"))
                if ev.eventType() == blpapi.Event.RESPONSE:
                    break
        except Exception:
            pass
        return 100

# ---------------------------------------------------------------------------
# Mock client (Black-Scholes based)
# ---------------------------------------------------------------------------

class MockBloombergClient:
    _SPOTS = {
        "AAPL": 250.30, "MSFT": 415.20, "GOOGL": 175.80, "AMZN": 195.60,
        "TSLA": 245.30, "SPY": 520.40, "QQQ": 445.10, "META": 560.75,
        "NVDA": 880.50, "IWM": 262.60, "UBER": 69.90, "QCOM": 141.20,
        "VST": 171.10, "SPX": 5204.00, "NFLX": 950.00,
    }
    _VOLS = {
        "AAPL": 0.22, "MSFT": 0.20, "GOOGL": 0.25, "AMZN": 0.28,
        "TSLA": 0.45, "SPY": 0.14, "QQQ": 0.18, "META": 0.32,
        "NVDA": 0.42, "IWM": 0.18, "UBER": 0.35, "QCOM": 0.30,
        "VST": 0.38, "SPX": 0.14, "NFLX": 0.34,
    }

    def connect(self):
        return True

    def get_spot(self, underlying):
        return self._SPOTS.get(underlying.upper(), 100.0)

    def get_option_quote(self, underlying, expiry, strike, option_type):
        spot = self.get_spot(underlying)
        base_vol = self._VOLS.get(underlying.upper(), 0.25)
        moneyness = strike / spot
        vol = base_vol + (0.05 * (1.0 - moneyness) if moneyness < 1.0 else 0.0)
        T = max((expiry - date.today()).days / 365.0, 0.001)

        # Black-Scholes
        d1 = (math.log(spot / strike) + (RISK_FREE_RATE + 0.5 * vol**2) * T) / (vol * math.sqrt(T))
        d2 = d1 - vol * math.sqrt(T)
        if option_type == "call":
            theo = spot * _norm_cdf(d1) - strike * math.exp(-RISK_FREE_RATE * T) * _norm_cdf(d2)
        else:
            theo = strike * math.exp(-RISK_FREE_RATE * T) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)

        spread_pct = 0.02 + 0.03 * abs(spot - strike) / spot
        half_spread = max(theo * spread_pct, 0.05)
        random.seed(int(strike * 100 + spot * 10))
        return OptionQuote(
            bid=round(max(theo - half_spread, 0.01), 2),
            bid_size=random.randint(100, 1000),
            offer=round(theo + half_spread, 2),
            offer_size=random.randint(100, 800),
        )

    def get_contract_multiplier(self, underlying):
        return 100


def _norm_cdf(x):
    """Standard normal CDF (no scipy dependency)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def _create_client(use_mock=False):
    if use_mock:
        return MockBloombergClient()
    client = BloombergClient()
    if client.connect():
        return client
    return MockBloombergClient()

# ---------------------------------------------------------------------------
# Flask HTTP server
# ---------------------------------------------------------------------------

app = Flask(__name__)
CORS(app)

_client = None
_is_mock = False

def _init(use_mock=False):
    global _client, _is_mock
    _client = _create_client(use_mock=use_mock)
    _is_mock = isinstance(_client, MockBloombergClient)

@app.route("/api/status")
def api_status():
    return jsonify({"status": "mock" if _is_mock else "live",
                     "port": request.host.split(":")[-1]})

@app.route("/api/spot/<ticker>")
def api_spot(ticker):
    if not _client:
        return jsonify({"error": "Not initialized"}), 503
    return jsonify({"spot": _client.get_spot(ticker.upper())})

@app.route("/api/multiplier/<ticker>")
def api_multiplier(ticker):
    if not _client:
        return jsonify({"error": "Not initialized"}), 503
    return jsonify({"multiplier": _client.get_contract_multiplier(ticker.upper())})

@app.route("/api/option_quotes", methods=["POST"])
def api_option_quotes():
    if not _client:
        return jsonify({"error": "Not initialized"}), 503
    data = request.get_json(silent=True)
    if not data or "underlying" not in data or "legs" not in data:
        return jsonify({"error": "Missing 'underlying' and 'legs'"}), 400

    underlying = data["underlying"].upper()
    spot = _client.get_spot(underlying)
    quotes = []
    for leg in data["legs"]:
        try:
            expiry = datetime.strptime(leg.get("expiry", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            quotes.append({"bid": 0, "bid_size": 0, "offer": 0, "offer_size": 0})
            continue
        q = _client.get_option_quote(underlying, expiry,
                                      float(leg.get("strike", 0)),
                                      leg.get("option_type", "call"))
        quotes.append({"bid": q.bid, "bid_size": q.bid_size,
                        "offer": q.offer, "offer_size": q.offer_size})

    return jsonify({"spot": spot, "quotes": quotes,
                     "multiplier": _client.get_contract_multiplier(underlying)})

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bloomberg Bridge")
    parser.add_argument("--port", type=int, default=BRIDGE_PORT)
    parser.add_argument("--mock", action="store_true",
                        help="Use mock data (no Bloomberg Terminal needed)")
    args = parser.parse_args()

    _init(use_mock=args.mock)
    mode = "mock" if _is_mock else "live"
    print(f"Bloomberg Bridge running on http://127.0.0.1:{args.port}")
    print(f"Mode: {mode}")
    print(f"Dashboard will auto-detect this bridge.")
    print()
    app.run(host="127.0.0.1", port=args.port)
