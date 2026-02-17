"""Dash web app entry point for the IDB options pricer dashboard.

Multi-user architecture:
- Username modal blocks UI until user enters a name (stored in session)
- Orders include `created_by` field showing which user added them
- Flask-SocketIO broadcasts blotter changes to all connected clients
- dcc.Interval provides fallback polling if WebSocket disconnects
"""

import logging
import os
import re
import threading
import time
import uuid
from collections import deque
from datetime import date, datetime

from dash import Dash, Input, Output, State, callback, ctx, html, no_update
from flask import Response, jsonify, send_file
from flask import request as flask_request
from flask_socketio import SocketIO, emit

from ..bloomberg import MockBloombergClient
from ..models import (
    LegMarketData,
    OptionLeg,
    OptionStructure,
    OptionType,
    ParsedOrder,
    QuoteSide,
    Side,
)
from ..order_store import load_orders as store_load_orders
from ..order_store import save_orders as store_save_orders
from ..parser import parse_expiry, parse_order
from ..settings import (
    BRIDGE_DEFAULT_PORT,
    DASHBOARD_DEBUG,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    MAX_USERS,
)
from ..structure_pricer import price_structure_from_market
from .layouts import (
    COLORS,
    _BLOTTER_COLUMNS,
    _EMPTY_ROW,
    _MODAL_OVERLAY_STYLE,
    _make_empty_rows,
    _to_blotter_rows,
    create_layout,
)

logger = logging.getLogger(__name__)

app = Dash(
    __name__,
    suppress_callback_exceptions=True,
    external_scripts=["https://cdn.socket.io/4.7.5/socket.io.min.js"],
)
app.title = "IDB Options Pricer"

# Set body/html background so no white bars appear at any viewport width
app.index_string = '''<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            html, body {
                background-color: ''' + COLORS["bg_page"] + ''';
                margin: 0;
                padding: 0;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>'''

app.layout = create_layout  # callable — Dash invokes per page load

# Flask-SocketIO for multi-user live updates
socketio = SocketIO(app.server, cors_allowed_origins="*", async_mode="threading")

# Track connected users (sid -> username)
_connected_users: dict[str, str] = {}


@socketio.on("connect")
def handle_connect():
    # Send current count immediately so client doesn't show stale "0 online"
    emit("user_count", {"count": len(_connected_users) + 1})
    logger.info("WebSocket client connected")


@socketio.on("disconnect")
def handle_disconnect():
    removed = _connected_users.pop(flask_request.sid, None)
    socketio.emit("user_count", {"count": len(_connected_users)}, to="/")
    logger.info("User '%s' disconnected (%d online)", removed or "?", len(_connected_users))


@socketio.on("register")
def handle_register(data):
    """Client sends username after modal submit. Reject if at capacity."""
    username = (data.get("username") or "").strip()
    if not username:
        return

    sid = flask_request.sid

    # Allow if this SID is already registered (re-register)
    if sid in _connected_users:
        _connected_users[sid] = username
        socketio.emit("user_count", {"count": len(_connected_users)}, to="/")
        return

    if len(_connected_users) >= MAX_USERS:
        emit("server_full", {"message": f"Server full ({MAX_USERS} users max). Try again later."})
        logger.warning("Rejected user '%s' — server full (%d/%d)", username, len(_connected_users), MAX_USERS)
        return

    _connected_users[sid] = username
    socketio.emit("user_count", {"count": len(_connected_users)}, to="/")
    logger.info("User '%s' registered (%d online)", username, len(_connected_users))


# ---------------------------------------------------------------------------
# Global rate limiter — 15 actions/second across all users
# ---------------------------------------------------------------------------

class _GlobalRateLimiter:
    """Thread-safe sliding window rate limiter."""

    def __init__(self, max_requests: int, window: float = 1.0):
        self.max_requests = max_requests
        self.window = window
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            while self._timestamps and self._timestamps[0] < now - self.window:
                self._timestamps.popleft()
            if len(self._timestamps) >= self.max_requests:
                return False
            self._timestamps.append(now)
            return True


_rate_limiter = _GlobalRateLimiter(max_requests=15)


@app.server.before_request
def _check_rate_limit():
    """Rate-limit Dash callback requests to 15/sec globally."""
    if flask_request.path == "/_dash-update-component":
        if not _rate_limiter.allow():
            return jsonify({"error": "Rate limit exceeded. Try again shortly."}), 429


# ---------------------------------------------------------------------------
# Route: serve standalone bridge as a downloadable .py file
# ---------------------------------------------------------------------------

_STANDALONE_BRIDGE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "standalone_bridge.py",
)


@app.server.route("/download/bloomberg_bridge.py")
def download_bridge():
    """Serve the standalone bridge script as a .py download."""
    return send_file(
        _STANDALONE_BRIDGE_PATH,
        mimetype="text/x-python",
        as_attachment=True,
        download_name="bloomberg_bridge.py",
    )


# Clientside callback: Enter key in textarea triggers pricing
app.clientside_callback(
    """
    function(id) {
        var textarea = document.getElementById("order-text");
        if (textarea && !textarea._enterBound) {
            textarea.addEventListener("keydown", function(e) {
                if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    var store = document.getElementById("textarea-enter");
                    var btn = document.getElementById("price-btn");
                    if (btn) btn.click();
                }
            });
            textarea._enterBound = true;
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("textarea-enter", "data"),
    Input("order-text", "value"),
)

# Clientside callback: Enter key in username input triggers submit
app.clientside_callback(
    """
    function(id) {
        var input = document.getElementById("username-input");
        if (input && !input._enterBound) {
            input.addEventListener("keydown", function(e) {
                if (e.key === "Enter") {
                    e.preventDefault();
                    var btn = document.getElementById("username-submit-btn");
                    if (btn) btn.click();
                }
            });
            input._enterBound = true;
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("username-error", "children"),
    Input("username-input", "value"),
    prevent_initial_call=True,
)

# Clientside callback: SocketIO client setup for live blotter sync
app.clientside_callback(
    """
    function(username) {
        if (!username) return [window.dash_clientside.no_update, window.dash_clientside.no_update];

        try {
            // Only connect once per session
            if (!window._sio && typeof io !== 'undefined') {
                var sio = io();
                window._sio = sio;

                sio.on('connect', function() {
                    sio.emit('register', {username: username});
                });

                sio.on('blotter_changed', function(data) {
                    // fallback polling will pick up changes
                });

                sio.on('user_count', function(data) {
                    var el = document.getElementById("online-count");
                    if (el) el.textContent = data.count + " online";
                });

                sio.on('server_full', function(data) {
                    var modal = document.getElementById("username-modal");
                    if (modal) modal.style.display = "flex";
                    var err = document.getElementById("username-error");
                    if (err) err.textContent = data.message || "Server full.";
                });
            } else if (window._sio) {
                // Re-register if username changed
                window._sio.emit('register', {username: username});
            }
        } catch(e) {
            console.warn("SocketIO setup failed:", e);
        }

        return [username, window.dash_clientside.no_update];
    }
    """,
    Output("user-display", "children"),
    Output("ws-online-count", "data"),
    Input("current-user", "data"),
    prevent_initial_call=True,
)

# Lazy mock fallback — only used when bridge is unreachable
_mock_client = None


def _get_mock_client():
    global _mock_client
    if _mock_client is None:
        _mock_client = MockBloombergClient()
    return _mock_client

# ---------------------------------------------------------------------------
# Reusable style constants
# ---------------------------------------------------------------------------

_HIDDEN = {"display": "none"}

_HEADER_VISIBLE_STYLE = {
    "backgroundColor": COLORS["bg_card"],
    "padding": "14px 20px",
    "borderRadius": "10px",
    "marginBottom": "14px",
    "border": f"1px solid {COLORS['border_accent']}",
    "display": "block",
}

_BROKER_VISIBLE_STYLE = {
    "backgroundColor": COLORS["bg_card"],
    "padding": "14px 20px",
    "borderRadius": "10px",
    "marginTop": "14px",
    "border": f"1px solid {COLORS['border']}",
    "display": "flex",
    "gap": "20px",
    "alignItems": "center",
}

_ORDER_INPUT_VISIBLE_STYLE = {
    "backgroundColor": COLORS["bg_card"],
    "padding": "14px 20px",
    "borderRadius": "10px",
    "marginTop": "14px",
    "border": f"1px solid {COLORS['border']}",
    "display": "block",
}

# Structure templates for pre-populating table rows.
STRUCTURE_TEMPLATES = {
    "single": [{"type": "C", "side": "B"}],
    "put_spread": [
        {"type": "P", "side": "S"},
        {"type": "P", "side": "B"},
    ],
    "call_spread": [
        {"type": "C", "side": "B"},
        {"type": "C", "side": "S"},
    ],
    "risk_reversal": [
        {"type": "P", "side": "S"},
        {"type": "C", "side": "B"},
    ],
    "straddle": [
        {"type": "C", "side": "B"},
        {"type": "P", "side": "B"},
    ],
    "strangle": [
        {"type": "P", "side": "B"},
        {"type": "C", "side": "B"},
    ],
    "butterfly": [
        {"type": "C", "side": "B"},
        {"type": "C", "side": "S", "qty": 2},
        {"type": "C", "side": "B"},
    ],
    "iron_condor": [
        {"type": "P", "side": "B"},
        {"type": "P", "side": "S"},
        {"type": "C", "side": "S"},
        {"type": "C", "side": "B"},
    ],
    "collar": [
        {"type": "P", "side": "B"},
        {"type": "C", "side": "S"},
    ],
}

# Map short codes to model enums
_TYPE_MAP = {"C": OptionType.CALL, "P": OptionType.PUT}
_SIDE_MAP = {"B": Side.BUY, "S": Side.SELL}



# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _serialize_parsed_order(order: ParsedOrder) -> dict:
    """Serialize a ParsedOrder into a JSON-safe dict for dcc.Store."""
    legs = []
    for leg in order.structure.legs:
        legs.append({
            "underlying": leg.underlying,
            "expiry": leg.expiry.isoformat(),
            "strike": leg.strike,
            "option_type": leg.option_type.value,
            "side": leg.side.value,
            "quantity": leg.quantity,
            "ratio": leg.ratio,
        })
    return {
        "underlying": order.underlying,
        "structure_name": order.structure.name,
        "structure_desc": order.structure.description,
        "legs": legs,
        "stock_ref": order.stock_ref,
        "delta": order.delta,
        "price": order.price,
        "quote_side": order.quote_side.value,
        "quantity": order.quantity,
        "raw_text": order.raw_text,
    }


def _deserialize_parsed_order(data: dict) -> ParsedOrder:
    """Reconstruct a ParsedOrder from a serialized dict."""
    legs = []
    for ld in data["legs"]:
        legs.append(OptionLeg(
            underlying=ld["underlying"],
            expiry=date.fromisoformat(ld["expiry"]),
            strike=ld["strike"],
            option_type=OptionType(ld["option_type"]),
            side=Side(ld["side"]),
            quantity=ld["quantity"],
            ratio=ld.get("ratio", 1),
        ))
    return ParsedOrder(
        underlying=data["underlying"],
        structure=OptionStructure(
            name=data["structure_name"],
            legs=legs,
            description=data.get("structure_desc", ""),
        ),
        stock_ref=data["stock_ref"],
        delta=data["delta"],
        price=data["price"],
        quote_side=QuoteSide(data["quote_side"]),
        quantity=data["quantity"],
        raw_text=data.get("raw_text", ""),
    )


def _build_market_data_request(order: ParsedOrder) -> dict:
    """Build a market data request dict for the bridge."""
    legs = []
    for leg in order.structure.legs:
        legs.append({
            "expiry": leg.expiry.isoformat(),
            "strike": leg.strike,
            "option_type": leg.option_type.value,
        })
    return {"underlying": order.underlying, "legs": legs}


def _price_with_market_data(order: ParsedOrder, mkt_response: dict) -> tuple:
    """Price a structure using market data from bridge or fallback.

    Returns (spot, leg_market, struct_data, multiplier).
    """
    spot = mkt_response.get("spot", 0)
    if spot is None or spot == 0:
        spot = order.stock_ref if order.stock_ref > 0 else 100.0

    quotes = mkt_response.get("quotes", [])
    leg_market: list[LegMarketData] = []
    for q in quotes:
        leg_market.append(LegMarketData(
            bid=q.get("bid", 0),
            bid_size=q.get("bid_size", 0),
            offer=q.get("offer", 0),
            offer_size=q.get("offer_size", 0),
        ))

    # Pad with empty LegMarketData if quotes < legs (shouldn't happen normally)
    while len(leg_market) < len(order.structure.legs):
        leg_market.append(LegMarketData())

    struct_data = price_structure_from_market(order, leg_market, spot)
    multiplier = mkt_response.get("multiplier", 100)
    return spot, leg_market, struct_data, multiplier


def _fetch_and_price_fallback(order: ParsedOrder) -> tuple:
    """Fallback: fetch from mock client when bridge is unreachable."""
    client = _get_mock_client()
    spot = client.get_spot(order.underlying)
    if spot is None or spot == 0:
        spot = order.stock_ref if order.stock_ref > 0 else 100.0

    quotes = []
    for leg in order.structure.legs:
        quote = client.get_option_quote(
            leg.underlying, leg.expiry, leg.strike, leg.option_type.value,
        )
        quotes.append({
            "bid": quote.bid,
            "bid_size": quote.bid_size,
            "offer": quote.offer,
            "offer_size": quote.offer_size,
        })

    multiplier = client.get_contract_multiplier(order.underlying)
    mkt_response = {"spot": spot, "quotes": quotes, "multiplier": multiplier}
    return _price_with_market_data(order, mkt_response)


def _build_table_data(order, leg_market, struct_data):
    """Build the unified table data (input + output columns) from priced order."""
    rows = []
    base_qty = (
        min(leg.quantity for leg in order.structure.legs)
        if order.structure.legs else 1
    )

    for i, (leg, mkt) in enumerate(zip(order.structure.legs, leg_market)):
        type_code = "C" if leg.option_type == OptionType.CALL else "P"
        side_code = "B" if leg.side == Side.BUY else "S"
        exp_str = leg.expiry.strftime("%b%y") if leg.expiry else ""
        ratio = leg.quantity // base_qty

        mid = (mkt.bid + mkt.offer) / 2.0 if mkt.bid > 0 and mkt.offer > 0 else 0.0
        rows.append({
            "leg": f"Leg {i + 1}",
            "expiry": exp_str,
            "strike": leg.strike,
            "type": type_code,
            "side": side_code,
            "qty": ratio,
            "bid_size": str(mkt.bid_size),
            "bid": f"{mkt.bid:.2f}",
            "mid": f"{mid:.2f}",
            "offer": f"{mkt.offer:.2f}",
            "offer_size": str(mkt.offer_size),
        })

    # Structure summary row
    rows.append({
        "leg": "Structure",
        "expiry": "", "strike": "", "type": "", "side": "", "qty": "",
        "bid_size": str(struct_data.structure_bid_size),
        "bid": f"{abs(struct_data.structure_bid):.2f}",
        "mid": f"{abs(struct_data.structure_mid):.2f}",
        "offer": f"{abs(struct_data.structure_offer):.2f}",
        "offer_size": str(struct_data.structure_offer_size),
    })

    return rows


def _build_header_and_extras(order, spot, struct_data, multiplier):
    """Build order header, broker quote, current-structure store, order input style."""
    header_items = []
    structure_name = order.structure.name.upper()
    header_items.append(
        html.Span(
            f"{order.underlying} {structure_name}",
            style={"color": COLORS["text_accent"], "fontWeight": "bold", "fontSize": "17px"},
        )
    )
    if order.stock_ref > 0:
        header_items.append(html.Span(f"Tie: ${order.stock_ref:.2f}"))
    header_items.append(html.Span(f"Stock: ${spot:.2f}"))
    if order.delta != 0:
        header_items.append(html.Span(f"Delta: {order.delta:+.0f}"))

    broker_style = _HIDDEN
    broker_content = []
    if order.price > 0:
        side_label = order.quote_side.value.upper()
        broker_content = [
            html.Span(
                f"Broker: {order.price:.2f} {side_label}",
                style={"fontSize": "16px", "marginRight": "30px"},
            ),
            html.Span(
                f"Screen Mid: {abs(struct_data.structure_mid):.2f}",
                style={"fontSize": "16px", "marginRight": "30px"},
            ),
        ]
        edge = order.price - abs(struct_data.structure_mid)
        edge_color = COLORS["positive"] if edge > 0 else COLORS["negative"]
        broker_content.append(
            html.Span(
                f"Edge: {edge:+.2f}",
                style={"fontSize": "16px", "color": edge_color, "fontWeight": "bold"},
            )
        )
        broker_style = _BROKER_VISIBLE_STYLE

    leg_details = []
    for leg in order.structure.legs:
        type_str = leg.option_type.value[0].upper()
        exp_str = leg.expiry.strftime("%b%y") if leg.expiry else ""
        leg_details.append(f"{leg.strike:.0f}{type_str} {exp_str}")
    structure_detail = " / ".join(leg_details)

    current_data = {
        "underlying": order.underlying,
        "structure_name": structure_name,
        "structure_detail": structure_detail,
        "bid": abs(struct_data.structure_bid),
        "mid": abs(struct_data.structure_mid),
        "offer": abs(struct_data.structure_offer),
        "bid_size": struct_data.structure_bid_size,
        "offer_size": struct_data.structure_offer_size,
        "multiplier": multiplier,
    }

    return (
        _HEADER_VISIBLE_STYLE, header_items,
        broker_style, broker_content,
        current_data, _ORDER_INPUT_VISIBLE_STYLE,
    )


def _parse_expiry_str(expiry_str: str) -> date:
    """Parse an expiry string like 'Jun26' or 'Mar27' into a date."""
    s = expiry_str.strip()
    m = re.match(r'^([A-Za-z]{3})(\d{2})?$', s)
    if not m:
        raise ValueError(f"Invalid expiry format: '{expiry_str}'. Use e.g. Jun26, Mar27")
    month_str = m.group(1)
    year_str = m.group(2)
    return parse_expiry(month_str, year_str)


def _build_legs_from_table(table_data, underlying, order_qty):
    """Parse table rows into OptionLeg list. Returns (legs, error_msg) tuple."""
    leg_rows = [r for r in (table_data or []) if r.get("leg", "").startswith("Leg")]

    legs: list[OptionLeg] = []
    for i, row in enumerate(leg_rows):
        expiry_str = str(row.get("expiry", "")).strip()
        strike_val = row.get("strike")
        type_val = str(row.get("type", "")).strip()
        side_val = str(row.get("side", "")).strip()
        qty_val = row.get("qty")

        row_has_data = bool(expiry_str or strike_val or type_val or side_val)
        if not row_has_data:
            continue

        if not expiry_str or not strike_val or type_val not in ("C", "P") or side_val not in ("B", "S"):
            return None, None  # Incomplete row — caller decides how to handle

        try:
            expiry = _parse_expiry_str(expiry_str)
        except ValueError as e:
            return None, f"Leg {i + 1}: {e}"

        qty = int(qty_val) if qty_val else 1
        legs.append(OptionLeg(
            underlying=underlying,
            expiry=expiry,
            strike=float(strike_val),
            option_type=_TYPE_MAP[type_val],
            side=_SIDE_MAP[side_val],
            quantity=qty * order_qty,
            ratio=qty,
        ))

    return legs, None


# ---------------------------------------------------------------------------
# Callback: paste-to-parse pricing
# ---------------------------------------------------------------------------

@callback(
    Output("parse-error", "children"),
    Output("pricing-context", "data"),
    Output("market-data-request", "data"),
    Output("fetch-trigger", "data"),
    Output("manual-underlying", "value"),
    Output("manual-structure-type", "value"),
    Output("manual-stock-ref", "value"),
    Output("manual-delta", "value"),
    Output("manual-broker-price", "value"),
    Output("manual-quote-side", "value"),
    Output("manual-quantity", "value"),
    Output("suppress-template", "data"),
    Output("auto-price-suppress", "data"),
    Input("price-btn", "n_clicks"),
    State("order-text", "value"),
    State("fetch-trigger", "data"),
    prevent_initial_call=True,
)
def parse_order_step(n_clicks, order_text, current_trigger):
    """Phase 1: Parse order text and request market data from bridge."""
    noop_tail = (
        no_update, no_update, no_update,  # pricing-context, mkt-request, fetch-trigger
        no_update, no_update,  # underlying, structure-type
        no_update, no_update,  # stock-ref, delta
        no_update, no_update,  # broker-price, quote-side
        no_update,             # quantity
        no_update, no_update,  # suppress-template, auto-price-suppress
    )

    if not order_text:
        return ("Please enter an order.", *noop_tail)

    try:
        order = parse_order(order_text)
    except ValueError as e:
        return (str(e), *noop_tail)

    pricing_ctx = _serialize_parsed_order(order)
    mkt_request = _build_market_data_request(order)
    new_trigger = (current_trigger or 0) + 1

    struct_name = order.structure.name.lower().replace(" ", "_")
    struct_dropdown = struct_name if struct_name in STRUCTURE_TEMPLATES else None

    return (
        "",                         # parse-error
        pricing_ctx,                # pricing-context
        mkt_request,                # market-data-request
        new_trigger,                # fetch-trigger (incremented)
        order.underlying,           # manual-underlying
        struct_dropdown,            # manual-structure-type
        order.stock_ref if order.stock_ref > 0 else None,
        order.delta if order.delta != 0 else None,
        order.price if order.price > 0 else None,
        order.quote_side.value,     # manual-quote-side
        order.quantity if order.quantity > 0 else None,
        True,                       # suppress-template
        True,                       # auto-price-suppress
    )


# ---------------------------------------------------------------------------
# Phase 2: Clientside JS — fetch market data from Bloomberg Bridge
# ---------------------------------------------------------------------------

app.clientside_callback(
    """
    async function(trigger, request, port) {
        if (!trigger || !request) {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }

        var bridgePort = port || 8195;
        var url = "http://127.0.0.1:" + bridgePort + "/api/option_quotes";

        try {
            var resp = await fetch(url, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(request),
                signal: AbortSignal.timeout(5000),
            });
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            var data = await resp.json();
            return [data, "bridge"];
        } catch (e) {
            // Bridge unreachable — signal fallback
            return [{"_fallback": true, "request": request}, "fallback"];
        }
    }
    """,
    Output("market-data-response", "data"),
    Output("market-data-source", "data"),
    Input("fetch-trigger", "data"),
    State("market-data-request", "data"),
    State("bridge-port", "data"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Phase 3: Price with market data (from bridge or fallback)
# ---------------------------------------------------------------------------

@callback(
    Output("pricing-display", "data"),
    Output("order-header", "style"),
    Output("order-header-content", "children"),
    Output("broker-quote-section", "style"),
    Output("broker-quote-content", "children"),
    Output("current-structure", "data"),
    Output("order-input-section", "style"),
    Input("market-data-response", "data"),
    State("pricing-context", "data"),
    prevent_initial_call=True,
)
def price_with_market_data(mkt_response, pricing_ctx):
    """Phase 3: Use market data to price the structure and update display."""
    if not mkt_response or not pricing_ctx:
        return (no_update,) * 7

    order = _deserialize_parsed_order(pricing_ctx)

    if mkt_response.get("_fallback"):
        # Bridge unreachable — use server-side mock
        spot, leg_market, struct_data, multiplier = _fetch_and_price_fallback(order)
    else:
        spot, leg_market, struct_data, multiplier = _price_with_market_data(order, mkt_response)

    table_data = _build_table_data(order, leg_market, struct_data)
    header_style, header_items, broker_style, broker_content, current_data, order_input_style = (
        _build_header_and_extras(order, spot, struct_data, multiplier)
    )

    return (
        table_data,
        header_style,
        header_items,
        broker_style,
        broker_content,
        current_data,
        order_input_style,
    )


# ---------------------------------------------------------------------------
# Callback: structure template pre-population
# ---------------------------------------------------------------------------

@callback(
    Output("pricing-display", "data", allow_duplicate=True),
    Output("suppress-template", "data", allow_duplicate=True),
    Output("auto-price-suppress", "data", allow_duplicate=True),
    Input("manual-structure-type", "value"),
    State("suppress-template", "data"),
    prevent_initial_call=True,
)
def populate_table_template(structure_type, suppress):
    if suppress:
        return no_update, False, no_update

    template = STRUCTURE_TEMPLATES.get(structure_type, [])
    if not template:
        return no_update, False, no_update

    rows = []
    for i, t in enumerate(template):
        rows.append({
            **_EMPTY_ROW,
            "leg": f"Leg {i + 1}",
            "type": t["type"],
            "side": t["side"],
            "qty": t.get("qty", 1),
        })
    return rows, False, True


# ---------------------------------------------------------------------------
# Callback: add/remove table rows
# ---------------------------------------------------------------------------

@callback(
    Output("pricing-display", "data", allow_duplicate=True),
    Output("auto-price-suppress", "data", allow_duplicate=True),
    Input("add-row-btn", "n_clicks"),
    Input("remove-row-btn", "n_clicks"),
    State("pricing-display", "data"),
    prevent_initial_call=True,
)
def toggle_table_rows(add_clicks, remove_clicks, current_data):
    triggered = ctx.triggered_id
    rows = [r for r in (current_data or []) if r.get("leg") != "Structure"]

    if triggered == "add-row-btn":
        n = len(rows) + 1
        rows.append({**_EMPTY_ROW, "leg": f"Leg {n}"})
    elif triggered == "remove-row-btn" and len(rows) > 1:
        rows.pop()

    return rows, True


# ---------------------------------------------------------------------------
# Callback: auto-price from table
# ---------------------------------------------------------------------------

@callback(
    Output("table-error", "children"),
    Output("pricing-context", "data", allow_duplicate=True),
    Output("market-data-request", "data", allow_duplicate=True),
    Output("fetch-trigger", "data", allow_duplicate=True),
    Output("auto-price-suppress", "data", allow_duplicate=True),
    Input("pricing-display", "data_timestamp"),
    Input("manual-underlying", "value"),
    State("auto-price-suppress", "data"),
    State("pricing-display", "data"),
    State("manual-structure-type", "value"),
    State("manual-stock-ref", "value"),
    State("manual-delta", "value"),
    State("manual-broker-price", "value"),
    State("manual-quote-side", "value"),
    State("manual-quantity", "value"),
    State("fetch-trigger", "data"),
    prevent_initial_call=True,
)
def auto_price_request(data_ts, underlying, suppress,
                       table_data, struct_type, stock_ref,
                       delta, broker_price, quote_side_val, order_qty,
                       current_trigger):
    """Auto-price from table edits — Phase 1: build request, trigger fetch."""
    noop = ("",) + (no_update,) * 3 + (False,)

    if suppress:
        return noop

    if not underlying or not underlying.strip():
        return noop

    underlying = underlying.strip().upper()
    order_qty_val = int(order_qty) if order_qty else 1

    legs, err_msg = _build_legs_from_table(table_data, underlying, order_qty_val)

    if err_msg:
        return (err_msg,) + (no_update,) * 3 + (False,)

    if legs is None or len(legs) == 0:
        return noop

    struct_name = struct_type.replace("_", " ") if struct_type else "custom"
    order = ParsedOrder(
        underlying=underlying,
        structure=OptionStructure(name=struct_name, legs=legs, description="Table entry"),
        stock_ref=float(stock_ref) if stock_ref else 0.0,
        delta=float(delta) if delta else 0.0,
        price=float(broker_price) if broker_price else 0.0,
        quote_side=QuoteSide(quote_side_val) if quote_side_val else QuoteSide.BID,
        quantity=order_qty_val,
        raw_text="Table entry",
    )

    pricing_ctx = _serialize_parsed_order(order)
    mkt_request = _build_market_data_request(order)
    new_trigger = (current_trigger or 0) + 1

    return (
        "",                 # table-error
        pricing_ctx,        # pricing-context
        mkt_request,        # market-data-request
        new_trigger,        # fetch-trigger
        True,               # auto-price-suppress (prevent self-loop)
    )


# ---------------------------------------------------------------------------
# Callback: clear / reset (does NOT clear the order blotter)
# ---------------------------------------------------------------------------

@callback(
    Output("pricing-display", "data", allow_duplicate=True),
    Output("order-text", "value"),
    Output("manual-underlying", "value", allow_duplicate=True),
    Output("manual-structure-type", "value", allow_duplicate=True),
    Output("manual-stock-ref", "value", allow_duplicate=True),
    Output("manual-delta", "value", allow_duplicate=True),
    Output("manual-broker-price", "value", allow_duplicate=True),
    Output("manual-quote-side", "value", allow_duplicate=True),
    Output("manual-quantity", "value", allow_duplicate=True),
    Output("order-header", "style", allow_duplicate=True),
    Output("order-header-content", "children", allow_duplicate=True),
    Output("broker-quote-section", "style", allow_duplicate=True),
    Output("broker-quote-content", "children", allow_duplicate=True),
    Output("current-structure", "data", allow_duplicate=True),
    Output("order-input-section", "style", allow_duplicate=True),
    Output("parse-error", "children", allow_duplicate=True),
    Output("table-error", "children", allow_duplicate=True),
    Output("auto-price-suppress", "data", allow_duplicate=True),
    Input("clear-btn", "n_clicks"),
    prevent_initial_call=True,
)
def clear_all(n_clicks):
    return (
        _make_empty_rows(2),  # pricing-display
        "",                   # order-text
        None,                 # manual-underlying
        None,                 # manual-structure-type
        None,                 # manual-stock-ref
        None,                 # manual-delta
        None,                 # manual-broker-price
        None,                 # manual-quote-side (neutral)
        None,                 # manual-quantity (empty)
        _HIDDEN,              # order-header style
        [],                   # order-header-content
        _HIDDEN,              # broker-quote-section style
        [],                   # broker-quote-content
        None,                 # current-structure
        _HIDDEN,              # order-input-section style
        "",                   # parse-error
        "",                   # table-error
        True,                 # auto-price-suppress
    )


# ---------------------------------------------------------------------------
# Callback: add order to blotter
# ---------------------------------------------------------------------------

@callback(
    Output("blotter-table", "data"),
    Output("order-store", "data"),
    Output("order-error", "children"),
    Output("order-side", "value"),
    Output("order-size", "value"),
    Output("blotter-edit-suppress", "data"),
    Input("add-order-btn", "n_clicks"),
    State("current-structure", "data"),
    State("order-store", "data"),
    State("current-user", "data"),
    # Capture pricer state for recall
    State("pricing-display", "data"),
    State("manual-underlying", "value"),
    State("manual-structure-type", "value"),
    State("manual-stock-ref", "value"),
    State("manual-delta", "value"),
    State("manual-broker-price", "value"),
    State("manual-quote-side", "value"),
    State("manual-quantity", "value"),
    prevent_initial_call=True,
)
def add_order(n_clicks, current_data, existing_orders, current_user,
              table_data, toolbar_underlying, toolbar_struct, toolbar_ref,
              toolbar_delta, toolbar_broker_px, toolbar_quote_side, toolbar_qty):
    if not current_data:
        return no_update, no_update, "Price a structure first.", no_update, no_update, no_update

    # Map toolbar side to blotter side
    side_map = {"bid": "Bid", "offer": "Offered"}
    blotter_side = side_map.get(toolbar_quote_side, "")
    size_str = str(int(toolbar_qty)) if toolbar_qty else ""
    mid = current_data["mid"]

    order_record = {
        "id": str(uuid.uuid4()),
        "added_time": datetime.now().strftime("%H:%M"),
        "created_by": current_user or "",
        "underlying": current_data["underlying"],
        "structure": f"{current_data['structure_name']} {current_data['structure_detail']}",
        "bid_size": str(current_data["bid_size"]),
        "bid": f"{current_data['bid']:.2f}",
        "mid": f"{mid:.2f}",
        "offer": f"{current_data['offer']:.2f}",
        "offer_size": str(current_data["offer_size"]),
        "side": blotter_side,
        "size": size_str,
        "traded": "No",
        "bought_sold": "",
        "traded_price": "",
        "initiator": "",
        "pnl": "",
        "multiplier": current_data.get("multiplier", 100),
        # Recall data
        "_table_data": table_data,
        "_underlying": toolbar_underlying,
        "_structure_type": toolbar_struct,
        "_stock_ref": toolbar_ref,
        "_delta": toolbar_delta,
        "_broker_price": toolbar_broker_px,
        "_quote_side": toolbar_quote_side,
        "_quantity": toolbar_qty,
        "_current_structure": current_data,
    }

    orders = existing_orders or []
    orders.append(order_record)

    # Persist to SQLite
    store_save_orders(orders)

    # Broadcast to other clients via WebSocket
    socketio.emit("blotter_changed", {"action": "added"}, to="/")

    return _to_blotter_rows(orders), orders, "", None, None, True


# ---------------------------------------------------------------------------
# Callback: show delete confirmation modal when X column is clicked
# ---------------------------------------------------------------------------

@callback(
    Output("delete-confirm-modal", "style"),
    Output("pending-delete-id", "data"),
    Output("delete-confirm-detail", "children"),
    Input("blotter-table", "active_cell"),
    State("blotter-table", "data"),
    prevent_initial_call=True,
)
def show_delete_modal(active_cell, blotter_data):
    """Show confirmation modal when user clicks the X column."""
    if not active_cell or not blotter_data:
        return no_update, no_update, no_update

    # Only trigger on the delete column
    if active_cell.get("column_id") != "delete":
        return {"display": "none"}, None, ""

    row_idx = active_cell["row"]
    if row_idx >= len(blotter_data):
        return no_update, no_update, no_update

    row = blotter_data[row_idx]
    order_id = row.get("id")
    if not order_id:
        return no_update, no_update, no_update

    detail = f"{row.get('underlying', '')} {row.get('structure', '')}"
    return {"display": "block"}, order_id, detail


@callback(
    Output("blotter-table", "data", allow_duplicate=True),
    Output("order-store", "data", allow_duplicate=True),
    Output("delete-confirm-modal", "style", allow_duplicate=True),
    Output("pending-delete-id", "data", allow_duplicate=True),
    Output("blotter-edit-suppress", "data", allow_duplicate=True),
    Input("delete-confirm-btn", "n_clicks"),
    State("pending-delete-id", "data"),
    State("order-store", "data"),
    prevent_initial_call=True,
)
def confirm_delete_order(n_clicks, pending_id, orders):
    """Actually delete the order after user confirms."""
    if not pending_id or not orders:
        return no_update, no_update, {"display": "none"}, None, no_update

    updated_orders = [o for o in orders if o.get("id") != pending_id]

    # Persist to SQLite
    store_save_orders(updated_orders)

    # Broadcast to other clients
    socketio.emit("blotter_changed", {"action": "deleted"}, to="/")

    return _to_blotter_rows(updated_orders), updated_orders, {"display": "none"}, None, True


@callback(
    Output("delete-confirm-modal", "style", allow_duplicate=True),
    Output("pending-delete-id", "data", allow_duplicate=True),
    Input("delete-cancel-btn", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_delete_order(n_clicks):
    """Hide the delete confirmation modal."""
    return {"display": "none"}, None


# ---------------------------------------------------------------------------
# Callback: sync blotter edits (editable cells) + PnL auto-calc
# ---------------------------------------------------------------------------

@callback(
    Output("order-store", "data", allow_duplicate=True),
    Output("blotter-table", "data", allow_duplicate=True),
    Output("blotter-edit-suppress", "data", allow_duplicate=True),
    Input("blotter-table", "data_timestamp"),
    State("blotter-table", "data"),
    State("order-store", "data"),
    State("blotter-edit-suppress", "data"),
    prevent_initial_call=True,
)
def sync_blotter_edits(data_ts, blotter_data, orders, suppress):
    if suppress:
        return no_update, no_update, False

    if not blotter_data or not orders:
        return no_update, no_update, False

    # Build lookup by id
    order_map = {o["id"]: o for o in orders if "id" in o}

    changed = False
    editable_fields = ("side", "size", "traded", "bought_sold", "traded_price", "initiator")

    for row in blotter_data:
        order_id = row.get("id")
        if not order_id or order_id not in order_map:
            continue

        stored = order_map[order_id]

        # Sync editable fields from blotter back to store
        for field in editable_fields:
            new_val = row.get(field)
            if new_val != stored.get(field):
                stored[field] = new_val
                changed = True

        # PnL only relevant for traded orders
        if (stored.get("traded") == "Yes"
                and stored.get("traded_price") not in (None, "")
                and stored.get("bought_sold") in ("Bought", "Sold")):
            try:
                mid = float(stored.get("mid", 0))
                tp = float(stored["traded_price"])
                sz = int(stored.get("size", 0))
                mult = stored.get("multiplier", 100)
                if stored["bought_sold"] == "Bought":
                    pnl = (mid - tp) * sz * mult
                else:
                    pnl = (tp - mid) * sz * mult
                pnl_str = f"{pnl:+,.0f}"
            except (ValueError, TypeError):
                pnl_str = ""
            if stored.get("pnl") != pnl_str:
                stored["pnl"] = pnl_str
                changed = True
        elif stored.get("traded") != "Yes" and stored.get("pnl") not in (None, ""):
            stored["pnl"] = ""
            changed = True

    if not changed:
        return no_update, no_update, False

    updated_orders = list(order_map.values())

    # Persist to SQLite
    store_save_orders(updated_orders)

    # Broadcast to other clients via WebSocket
    socketio.emit("blotter_changed", {"action": "updated"}, to="/")

    return updated_orders, _to_blotter_rows(updated_orders), True


# ---------------------------------------------------------------------------
# Callback: toggle column panel visibility
# ---------------------------------------------------------------------------

@callback(
    Output("column-toggle-panel", "style"),
    Input("column-toggle-btn", "n_clicks"),
    State("column-toggle-panel", "style"),
    prevent_initial_call=True,
)
def toggle_column_panel(n_clicks, current_style):
    if current_style.get("display") == "none":
        return {"display": "block"}
    return {"display": "none"}


# ---------------------------------------------------------------------------
# Callback: update visible blotter columns
# ---------------------------------------------------------------------------

@callback(
    Output("blotter-table", "columns"),
    Output("visible-columns", "data"),
    Input("column-checklist", "value"),
    prevent_initial_call=True,
)
def update_visible_columns(selected_columns):
    # Always include the delete column first, then user-selected columns
    visible = [_BLOTTER_COLUMNS[0]] + [
        c for c in _BLOTTER_COLUMNS[1:] if c["id"] in selected_columns
    ]
    return visible, selected_columns


# ---------------------------------------------------------------------------
# Callback: recall order from blotter into pricer
# ---------------------------------------------------------------------------

@callback(
    Output("pricing-display", "data", allow_duplicate=True),
    Output("manual-underlying", "value", allow_duplicate=True),
    Output("manual-structure-type", "value", allow_duplicate=True),
    Output("manual-stock-ref", "value", allow_duplicate=True),
    Output("manual-delta", "value", allow_duplicate=True),
    Output("manual-broker-price", "value", allow_duplicate=True),
    Output("manual-quote-side", "value", allow_duplicate=True),
    Output("manual-quantity", "value", allow_duplicate=True),
    Output("order-header", "style", allow_duplicate=True),
    Output("order-header-content", "children", allow_duplicate=True),
    Output("broker-quote-section", "style", allow_duplicate=True),
    Output("broker-quote-content", "children", allow_duplicate=True),
    Output("current-structure", "data", allow_duplicate=True),
    Output("order-input-section", "style", allow_duplicate=True),
    Output("suppress-template", "data", allow_duplicate=True),
    Output("auto-price-suppress", "data", allow_duplicate=True),
    Input("blotter-table", "active_cell"),
    State("blotter-table", "data"),
    State("order-store", "data"),
    prevent_initial_call=True,
)
def recall_order(active_cell, blotter_data, orders):
    if not active_cell or not orders or not blotter_data:
        return (no_update,) * 16

    # Ignore clicks on the delete column (handled by show_delete_modal)
    if active_cell.get("column_id") == "delete":
        return (no_update,) * 16

    row_idx = active_cell["row"]
    if row_idx >= len(blotter_data):
        return (no_update,) * 16

    # Get the order id from the displayed row (handles sorted tables)
    clicked_id = blotter_data[row_idx].get("id")
    if not clicked_id:
        return (no_update,) * 16

    # Find the full order in the store by id
    order = next((o for o in orders if o.get("id") == clicked_id), None)
    if not order:
        return (no_update,) * 16

    table_data = order.get("_table_data")
    if not table_data:
        return (no_update,) * 16

    current_data = order.get("_current_structure")

    header_style = _HIDDEN
    header_items = []
    broker_style = _HIDDEN
    broker_content = []
    order_input_style = _HIDDEN

    if current_data:
        header_items = [
            html.Span(
                f"{current_data['underlying']} {current_data['structure_name']}",
                style={"color": COLORS["text_accent"], "fontWeight": "bold", "fontSize": "17px"},
            ),
        ]
        header_style = _HEADER_VISIBLE_STYLE
        order_input_style = _ORDER_INPUT_VISIBLE_STYLE

        broker_px = order.get("_broker_price")
        if broker_px and float(broker_px) > 0:
            quote_side = (order.get("_quote_side") or "bid").upper()
            mid = current_data["mid"]
            edge = float(broker_px) - mid
            edge_color = COLORS["positive"] if edge > 0 else COLORS["negative"]
            broker_content = [
                html.Span(
                    f"Broker: {float(broker_px):.2f} {quote_side}",
                    style={"fontSize": "16px", "marginRight": "30px"},
                ),
                html.Span(
                    f"Screen Mid: {mid:.2f}",
                    style={"fontSize": "16px", "marginRight": "30px"},
                ),
                html.Span(
                    f"Edge: {edge:+.2f}",
                    style={"fontSize": "16px", "color": edge_color, "fontWeight": "bold"},
                ),
            ]
            broker_style = _BROKER_VISIBLE_STYLE

    return (
        table_data,
        order.get("_underlying"),
        order.get("_structure_type"),
        order.get("_stock_ref"),
        order.get("_delta"),
        order.get("_broker_price"),
        order.get("_quote_side"),
        order.get("_quantity"),
        header_style,
        header_items,
        broker_style,
        broker_content,
        current_data,
        order_input_style,
        True,   # suppress-template
        True,   # auto-price-suppress
    )


# ---------------------------------------------------------------------------
# Callback: username modal — submit username, hide modal
# ---------------------------------------------------------------------------

@callback(
    Output("username-modal", "style"),
    Output("current-user", "data"),
    Output("username-error", "children", allow_duplicate=True),
    Output("online-count", "children", allow_duplicate=True),
    Input("username-submit-btn", "n_clicks"),
    State("username-input", "value"),
    State("current-user", "data"),
    prevent_initial_call=True,
)
def submit_username(n_clicks, username_input, existing_user):
    name = (username_input or "").strip()
    if not name:
        return no_update, no_update, "Please enter your name.", no_update

    # +1 because this user's WebSocket register hasn't fired yet
    count = len(_connected_users) + (1 if not existing_user else 0)
    return {"display": "none"}, name, "", f"{count} online"


# ---------------------------------------------------------------------------
# Callback: restore username modal state on page load
# (if session already has a username, hide the modal immediately)
# ---------------------------------------------------------------------------

app.clientside_callback(
    """
    function(username) {
        if (username && username.length > 0) {
            return {"display": "none"};
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("username-modal", "style", allow_duplicate=True),
    Input("current-user", "data"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Callback: poll for blotter updates from other users
# ---------------------------------------------------------------------------

@callback(
    Output("blotter-table", "data", allow_duplicate=True),
    Output("order-store", "data", allow_duplicate=True),
    Output("blotter-edit-suppress", "data", allow_duplicate=True),
    Input("blotter-poll", "n_intervals"),
    State("order-store", "data"),
    prevent_initial_call=True,
)
def poll_blotter_updates(n_intervals, current_orders):
    """Periodically reload orders from SQLite to pick up changes from other users."""
    fresh_orders = store_load_orders()

    # Quick check: if order count hasn't changed and IDs match, skip update
    current_ids = {o.get("id") for o in (current_orders or [])}
    fresh_ids = {o.get("id") for o in fresh_orders}
    if current_ids == fresh_ids and len(current_orders or []) == len(fresh_orders):
        # Also check if any data changed (compare serialized form)
        return no_update, no_update, no_update

    return _to_blotter_rows(fresh_orders), fresh_orders, True


# ---------------------------------------------------------------------------
# Callback: update online count via poll (reliable server-side fallback)
# ---------------------------------------------------------------------------

@callback(
    Output("online-count", "children"),
    Input("blotter-poll", "n_intervals"),
    State("current-user", "data"),
    prevent_initial_call=True,
)
def update_online_count(n_intervals, current_user):
    count = len(_connected_users)
    if current_user:
        count = max(count, 1)
    return f"{count} online"


# ---------------------------------------------------------------------------
# Callback: change username — re-show the modal
# ---------------------------------------------------------------------------

@callback(
    Output("username-modal", "style", allow_duplicate=True),
    Output("username-input", "value"),
    Input("change-user-btn", "n_clicks"),
    State("current-user", "data"),
    prevent_initial_call=True,
)
def change_username(n_clicks, current_user):
    return _MODAL_OVERLAY_STYLE, current_user or ""


# ---------------------------------------------------------------------------
# Bloomberg Bridge status callbacks
# ---------------------------------------------------------------------------

# Periodic bridge status check — reuses blotter-poll 5s interval
app.clientside_callback(
    """
    async function(n_intervals, port) {
        var bridgePort = port || 8195;
        var url = "http://127.0.0.1:" + bridgePort + "/api/status";

        try {
            var resp = await fetch(url, {signal: AbortSignal.timeout(2000)});
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            var data = await resp.json();
            var status = data.status || "mock";
            var dotColor = status === "live" ? "#34d399" : "#fb923c";
            return [
                status,
                {"width":"8px","height":"8px","borderRadius":"50%","backgroundColor":dotColor,"display":"inline-block"},
                {"display": "none"},
            ];
        } catch(e) {
            return [
                "disconnected",
                {"width":"8px","height":"8px","borderRadius":"50%","backgroundColor":"#f87171","display":"inline-block"},
                {"display": "block"},
            ];
        }
    }
    """,
    Output("bridge-status", "data"),
    Output("bbg-status-dot", "style"),
    Output("bridge-banner", "style"),
    Input("blotter-poll", "n_intervals"),
    State("bridge-port", "data"),
    prevent_initial_call=True,
)

# Toggle settings panel on BBG indicator click
app.clientside_callback(
    """
    function(n_clicks, current_style) {
        if (!n_clicks) return window.dash_clientside.no_update;
        var visible = current_style && current_style.display !== "none";
        return {"display": visible ? "none" : "block"};
    }
    """,
    Output("bbg-settings-panel", "style"),
    Input("bbg-status-indicator", "n_clicks"),
    State("bbg-settings-panel", "style"),
    prevent_initial_call=True,
)

# Save bridge port to local storage + update command display
app.clientside_callback(
    """
    function(value) {
        if (!value) return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        var port = parseInt(value) || 8195;
        var cmd = "python bloomberg_bridge.py --port " + port;
        return [port, cmd];
    }
    """,
    Output("bridge-port", "data"),
    Output("bridge-cmd-display", "children"),
    Input("bridge-port-input", "value"),
    prevent_initial_call=True,
)

# Test connection button
app.clientside_callback(
    """
    async function(n_clicks, port) {
        if (!n_clicks) return window.dash_clientside.no_update;
        var bridgePort = port || 8195;
        var url = "http://127.0.0.1:" + bridgePort + "/api/status";

        try {
            var resp = await fetch(url, {signal: AbortSignal.timeout(3000)});
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            var data = await resp.json();
            return "Connected — " + data.status + " mode";
        } catch(e) {
            return "Connection failed — bridge not running on port " + bridgePort;
        }
    }
    """,
    Output("bridge-test-result", "children"),
    Input("bridge-test-btn", "n_clicks"),
    State("bridge-port", "data"),
    prevent_initial_call=True,
)


def main():
    """Run the dashboard with SocketIO for multi-user support."""
    socketio.run(
        app.server,
        host=DASHBOARD_HOST,
        port=DASHBOARD_PORT,
        debug=DASHBOARD_DEBUG,
        allow_unsafe_werkzeug=True,
    )


if __name__ == "__main__":
    main()
