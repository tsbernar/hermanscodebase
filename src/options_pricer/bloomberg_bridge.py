"""Bloomberg Bridge — local HTTP server wrapping blpapi for browser access.

Runs on the user's desktop alongside Bloomberg Terminal. Exposes a simple
REST API that the Dash dashboard fetches via clientside JavaScript.

Usage:
    python -m options_pricer.bloomberg_bridge [--port 8195] [--mock]
"""

import argparse
import logging
from datetime import date, datetime

from flask import Flask, jsonify, request
from flask_cors import CORS

from .bloomberg import OptionQuote, create_client
from .settings import BRIDGE_DEFAULT_PORT

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Initialized in main() or init_app()
_client = None
_is_mock = False


def init_app(use_mock: bool = False):
    """Initialize the Bloomberg client for the bridge."""
    global _client, _is_mock
    _client = create_client(use_mock=use_mock)
    _is_mock = isinstance(_client, type) and "Mock" in type(_client).__name__
    # More reliable check
    _is_mock = type(_client).__name__ == "MockBloombergClient"


@app.route("/api/status", methods=["GET"])
def status():
    """Return bridge status and whether Bloomberg is live or mock."""
    mode = "mock" if _is_mock else "live"
    return jsonify({"status": mode, "port": request.host.split(":")[-1]})


@app.route("/api/spot/<ticker>", methods=["GET"])
def spot(ticker):
    """Return spot price for a ticker."""
    if _client is None:
        return jsonify({"error": "Bridge not initialized"}), 503
    price = _client.get_spot(ticker.upper())
    return jsonify({"spot": price})


@app.route("/api/multiplier/<ticker>", methods=["GET"])
def multiplier(ticker):
    """Return contract multiplier for a ticker."""
    if _client is None:
        return jsonify({"error": "Bridge not initialized"}), 503
    mult = _client.get_contract_multiplier(ticker.upper())
    return jsonify({"multiplier": mult})


@app.route("/api/option_quotes", methods=["POST"])
def option_quotes():
    """Fetch spot + option quotes for a list of legs.

    Request body:
    {
        "underlying": "AAPL",
        "legs": [
            {"expiry": "2026-06-19", "strike": 240.0, "option_type": "put"},
            {"expiry": "2026-06-19", "strike": 220.0, "option_type": "put"}
        ]
    }

    Response:
    {
        "spot": 250.3,
        "quotes": [
            {"bid": 5.20, "bid_size": 300, "offer": 5.80, "offer_size": 250},
            ...
        ],
        "multiplier": 100
    }
    """
    if _client is None:
        return jsonify({"error": "Bridge not initialized"}), 503

    data = request.get_json(silent=True)
    if not data or "underlying" not in data or "legs" not in data:
        return jsonify({"error": "Missing 'underlying' and 'legs' in request body"}), 400

    underlying = data["underlying"].upper()
    spot_price = _client.get_spot(underlying)

    quotes = []
    for leg in data["legs"]:
        expiry_str = leg.get("expiry", "")
        strike = float(leg.get("strike", 0))
        option_type = leg.get("option_type", "call")

        # Parse expiry from ISO format
        try:
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            quotes.append({"bid": 0, "bid_size": 0, "offer": 0, "offer_size": 0})
            continue

        quote: OptionQuote = _client.get_option_quote(
            underlying, expiry, strike, option_type,
        )
        quotes.append({
            "bid": quote.bid,
            "bid_size": quote.bid_size,
            "offer": quote.offer,
            "offer_size": quote.offer_size,
        })

    mult = _client.get_contract_multiplier(underlying)
    return jsonify({"spot": spot_price, "quotes": quotes, "multiplier": mult})


def main():
    parser = argparse.ArgumentParser(description="Bloomberg Bridge HTTP server")
    parser.add_argument("--port", type=int, default=BRIDGE_DEFAULT_PORT,
                        help=f"Port to listen on (default: {BRIDGE_DEFAULT_PORT})")
    parser.add_argument("--mock", action="store_true",
                        help="Use mock Bloomberg data instead of live Terminal")
    args = parser.parse_args()

    init_app(use_mock=args.mock)

    logger.info("Bloomberg Bridge starting on port %d (mode: %s)",
                args.port, "mock" if _is_mock else "live")
    print(f"Bloomberg Bridge running on http://127.0.0.1:{args.port}")
    print(f"Mode: {'mock' if _is_mock else 'live'}")

    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
