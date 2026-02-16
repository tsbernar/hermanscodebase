"""Dash web app entry point for the IDB options pricer dashboard."""

import re
from datetime import date, datetime

from dash import Dash, Input, Output, State, callback, ctx, html, no_update

from ..bloomberg import create_client
from ..models import (
    LegMarketData,
    OptionLeg,
    OptionStructure,
    OptionType,
    ParsedOrder,
    QuoteSide,
    Side,
)
from ..parser import parse_expiry, parse_order
from ..structure_pricer import price_structure_from_market
from .layouts import _EMPTY_ROW, _make_empty_rows, create_layout

app = Dash(__name__, suppress_callback_exceptions=True)
app.title = "IDB Options Pricer"
app.layout = create_layout()

# Try live Bloomberg first, fall back to mock
_client = create_client(use_mock=False)

# ---------------------------------------------------------------------------
# Reusable style constants
# ---------------------------------------------------------------------------

_HIDDEN = {"display": "none"}

_HEADER_VISIBLE_STYLE = {
    "backgroundColor": "#1a1a2e",
    "padding": "12px 20px",
    "borderRadius": "6px",
    "marginBottom": "15px",
    "display": "block",
}

_BROKER_VISIBLE_STYLE = {
    "backgroundColor": "#1a1a2e",
    "padding": "15px 20px",
    "borderRadius": "6px",
    "marginTop": "15px",
    "display": "flex",
    "gap": "20px",
    "alignItems": "center",
}

_TRADE_INPUT_VISIBLE_STYLE = {
    "backgroundColor": "#1a1a2e",
    "padding": "15px 20px",
    "borderRadius": "6px",
    "marginTop": "15px",
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

# Error tail for price_order (outputs 3-17 when pricing fails)
_PRICE_ORDER_ERR_TAIL = (
    _HIDDEN, [],           # order-header style, content
    _HIDDEN, [],           # broker-quote style, content
    None,                  # current-structure
    _HIDDEN,               # trade-input-section
    no_update, no_update,  # underlying, structure-type
    no_update, no_update,  # stock-ref, delta
    no_update, no_update,  # broker-price, quote-side
    no_update,             # quantity
    False,                 # suppress-template
    True,                  # auto-price-suppress
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _fetch_and_price(order):
    """Fetch market data for each leg, price the structure, return outputs."""
    spot = _client.get_spot(order.underlying)
    if spot is None or spot == 0:
        spot = order.stock_ref if order.stock_ref > 0 else 100.0

    leg_market: list[LegMarketData] = []
    for leg in order.structure.legs:
        quote = _client.get_option_quote(
            leg.underlying, leg.expiry, leg.strike, leg.option_type.value,
        )
        leg_market.append(LegMarketData(
            bid=quote.bid,
            bid_size=quote.bid_size,
            offer=quote.offer,
            offer_size=quote.offer_size,
        ))

    struct_data = price_structure_from_market(order, leg_market, spot)
    multiplier = _client.get_contract_multiplier(order.underlying)
    return spot, leg_market, struct_data, multiplier


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
    """Build order header, broker quote, current-structure store, trade input style."""
    header_items = []
    structure_name = order.structure.name.upper()
    header_items.append(
        html.Span(
            f"{order.underlying} {structure_name}",
            style={"color": "#00d4ff", "fontWeight": "bold", "fontSize": "17px"},
        )
    )
    if order.stock_ref > 0:
        header_items.append(html.Span(f"Tie: ${order.stock_ref:.2f}"))
    header_items.append(html.Span(f"Stock: ${spot:.2f}"))
    if order.delta > 0:
        header_items.append(html.Span(f"Delta: +{order.delta:.0f}"))
    elif order.delta < 0:
        header_items.append(html.Span(f"Delta: {order.delta:.0f}"))

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
        edge_color = "#00ff88" if edge > 0 else "#ff4444"
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
        current_data, _TRADE_INPUT_VISIBLE_STYLE,
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
    Output("pricing-display", "data"),
    Output("order-header", "style"),
    Output("order-header-content", "children"),
    Output("broker-quote-section", "style"),
    Output("broker-quote-content", "children"),
    Output("current-structure", "data"),
    Output("trade-input-section", "style"),
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
    prevent_initial_call=True,
)
def price_order(n_clicks, order_text):
    if not order_text:
        return ("Please enter an order.", [], *_PRICE_ORDER_ERR_TAIL)

    try:
        order = parse_order(order_text)
    except ValueError as e:
        return (str(e), [], *_PRICE_ORDER_ERR_TAIL)

    spot, leg_market, struct_data, multiplier = _fetch_and_price(order)
    table_data = _build_table_data(order, leg_market, struct_data)
    header_style, header_items, broker_style, broker_content, current_data, trade_input_style = (
        _build_header_and_extras(order, spot, struct_data, multiplier)
    )

    struct_name = order.structure.name.lower().replace(" ", "_")
    struct_dropdown = struct_name if struct_name in STRUCTURE_TEMPLATES else None

    return (
        "",                         # parse-error
        table_data,                 # pricing-display data
        header_style,               # order-header style
        header_items,               # order-header-content
        broker_style,               # broker-quote-section style
        broker_content,             # broker-quote-content
        current_data,               # current-structure
        trade_input_style,          # trade-input-section style
        order.underlying,           # manual-underlying
        struct_dropdown,            # manual-structure-type
        order.stock_ref if order.stock_ref > 0 else None,
        order.delta if order.delta != 0 else None,
        order.price if order.price > 0 else None,
        order.quote_side.value,     # manual-quote-side
        order.quantity if order.quantity > 0 else 100,
        True,                       # suppress-template
        True,                       # auto-price-suppress
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
# Callback: auto-price from table (replaces manual price_from_table)
# ---------------------------------------------------------------------------

@callback(
    Output("table-error", "children"),
    Output("pricing-display", "data", allow_duplicate=True),
    Output("order-header", "style", allow_duplicate=True),
    Output("order-header-content", "children", allow_duplicate=True),
    Output("broker-quote-section", "style", allow_duplicate=True),
    Output("broker-quote-content", "children", allow_duplicate=True),
    Output("current-structure", "data", allow_duplicate=True),
    Output("trade-input-section", "style", allow_duplicate=True),
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
    prevent_initial_call=True,
)
def auto_price_from_table(data_ts, underlying, suppress,
                          table_data, struct_type, stock_ref,
                          delta, broker_price, quote_side_val, order_qty):
    # 9 outputs: table-error, pricing-display, header style/content,
    #            broker style/content, current-structure, trade-input, auto-suppress
    noop = ("",) + (no_update,) * 7 + (False,)

    if suppress:
        return noop

    if not underlying or not underlying.strip():
        return noop

    underlying = underlying.strip().upper()
    order_qty_val = int(order_qty) if order_qty else 100

    legs, err_msg = _build_legs_from_table(table_data, underlying, order_qty_val)

    if err_msg:
        # Genuine error (e.g. bad expiry format)
        return (err_msg,) + (no_update,) * 7 + (False,)

    if legs is None or len(legs) == 0:
        # Incomplete or empty rows — skip silently
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

    try:
        spot, leg_market, struct_data, multiplier = _fetch_and_price(order)
    except Exception as e:
        return (f"Pricing error: {e}",) + (no_update,) * 7 + (False,)

    new_table = _build_table_data(order, leg_market, struct_data)
    header_style, header_items, broker_style, broker_content, current_data, trade_input_style = (
        _build_header_and_extras(order, spot, struct_data, multiplier)
    )

    return (
        "",                 # table-error
        new_table,          # pricing-display data
        header_style,       # order-header style
        header_items,       # order-header-content
        broker_style,       # broker-quote-section style
        broker_content,     # broker-quote-content
        current_data,       # current-structure
        trade_input_style,  # trade-input-section style
        True,               # auto-price-suppress (prevent self-loop)
    )


# ---------------------------------------------------------------------------
# Callback: clear / reset
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
    Output("trade-input-section", "style", allow_duplicate=True),
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
        "bid",                # manual-quote-side (default)
        100,                  # manual-quantity (default)
        _HIDDEN,              # order-header style
        [],                   # order-header-content
        _HIDDEN,              # broker-quote-section style
        [],                   # broker-quote-content
        None,                 # current-structure
        _HIDDEN,              # trade-input-section style
        "",                   # parse-error
        "",                   # table-error
        True,                 # auto-price-suppress
    )


# ---------------------------------------------------------------------------
# Callback: add trade to blotter
# ---------------------------------------------------------------------------

@callback(
    Output("blotter-table", "data"),
    Output("trade-store", "data"),
    Output("trade-error", "children"),
    Output("trade-side", "value"),
    Output("trade-price", "value"),
    Output("trade-size", "value"),
    Input("add-trade-btn", "n_clicks"),
    State("current-structure", "data"),
    State("trade-side", "value"),
    State("trade-price", "value"),
    State("trade-size", "value"),
    State("trade-store", "data"),
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
def add_trade(n_clicks, current_data, side, traded_price, size, existing_trades,
              table_data, toolbar_underlying, toolbar_struct, toolbar_ref,
              toolbar_delta, toolbar_broker_px, toolbar_quote_side, toolbar_qty):
    if not current_data:
        return no_update, no_update, "Price a structure first.", no_update, no_update, no_update
    if not side:
        return no_update, no_update, "Select Buyer or Seller.", no_update, no_update, no_update
    if traded_price is None:
        return no_update, no_update, "Enter traded price.", no_update, no_update, no_update
    if size is None:
        return no_update, no_update, "Enter size.", no_update, no_update, no_update

    traded_price = float(traded_price)
    size = int(size)
    multiplier = current_data.get("multiplier", 100)
    mid = current_data["mid"]

    if side == "Buyer":
        pnl = (mid - traded_price) * size * multiplier
    else:
        pnl = (traded_price - mid) * size * multiplier

    display_row = {
        "underlying": current_data["underlying"],
        "structure": f"{current_data['structure_name']} {current_data['structure_detail']}",
        "bid_size": str(current_data["bid_size"]),
        "bid": f"{current_data['bid']:.2f}",
        "mid": f"{mid:.2f}",
        "offer": f"{current_data['offer']:.2f}",
        "offer_size": str(current_data["offer_size"]),
        "buyer_seller": side,
        "traded_price": f"{traded_price:.2f}",
        "size": str(size),
        "pnl": f"{pnl:+,.0f}",
        "added_time": datetime.now().strftime("%H:%M"),
    }

    full_record = {
        **display_row,
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

    trades = existing_trades or []
    trades.append(full_record)

    blotter_rows = [
        {k: v for k, v in t.items() if not k.startswith("_")}
        for t in trades
    ]

    return blotter_rows, trades, "", None, None, None


# ---------------------------------------------------------------------------
# Callback: recall trade from blotter into pricer
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
    Output("trade-input-section", "style", allow_duplicate=True),
    Output("suppress-template", "data", allow_duplicate=True),
    Output("auto-price-suppress", "data", allow_duplicate=True),
    Input("blotter-table", "active_cell"),
    State("trade-store", "data"),
    prevent_initial_call=True,
)
def recall_trade(active_cell, trades):
    if not active_cell or not trades:
        return (no_update,) * 16

    row_idx = active_cell["row"]
    if row_idx >= len(trades):
        return (no_update,) * 16

    trade = trades[row_idx]

    table_data = trade.get("_table_data")
    if not table_data:
        return (no_update,) * 16

    current_data = trade.get("_current_structure")

    header_style = _HIDDEN
    header_items = []
    broker_style = _HIDDEN
    broker_content = []
    trade_input_style = _HIDDEN

    if current_data:
        header_items = [
            html.Span(
                f"{current_data['underlying']} {current_data['structure_name']}",
                style={"color": "#00d4ff", "fontWeight": "bold", "fontSize": "17px"},
            ),
        ]
        header_style = _HEADER_VISIBLE_STYLE
        trade_input_style = _TRADE_INPUT_VISIBLE_STYLE

        broker_px = trade.get("_broker_price")
        if broker_px and float(broker_px) > 0:
            quote_side = (trade.get("_quote_side") or "bid").upper()
            mid = current_data["mid"]
            edge = float(broker_px) - mid
            edge_color = "#00ff88" if edge > 0 else "#ff4444"
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
        trade.get("_underlying"),
        trade.get("_structure_type"),
        trade.get("_stock_ref"),
        trade.get("_delta"),
        trade.get("_broker_price"),
        trade.get("_quote_side"),
        trade.get("_quantity"),
        header_style,
        header_items,
        broker_style,
        broker_content,
        current_data,
        trade_input_style,
        True,   # suppress-template
        True,   # auto-price-suppress
    )


def main():
    """Run the dashboard."""
    app.run(host="127.0.0.1", port=8050, debug=True)


if __name__ == "__main__":
    main()
