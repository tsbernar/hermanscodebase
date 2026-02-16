"""Dash web app entry point for the IDB options pricer dashboard."""

import re
import uuid
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
from ..order_store import add_order as store_add_order
from ..order_store import save_orders as store_save_orders
from ..parser import parse_expiry, parse_order
from ..structure_pricer import price_structure_from_market
from .layouts import (
    _BLOTTER_COLUMNS,
    _EMPTY_ROW,
    _make_empty_rows,
    create_layout,
)

app = Dash(__name__, suppress_callback_exceptions=True)
app.title = "IDB Options Pricer"
app.layout = create_layout  # callable — Dash invokes per page load

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

_ORDER_INPUT_VISIBLE_STYLE = {
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
    _HIDDEN,               # order-input-section
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
    """Build order header, broker quote, current-structure store, order input style."""
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
    Output("pricing-display", "data"),
    Output("order-header", "style"),
    Output("order-header-content", "children"),
    Output("broker-quote-section", "style"),
    Output("broker-quote-content", "children"),
    Output("current-structure", "data"),
    Output("order-input-section", "style"),
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
    header_style, header_items, broker_style, broker_content, current_data, order_input_style = (
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
        order_input_style,          # order-input-section style
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
    Output("pricing-display", "data", allow_duplicate=True),
    Output("order-header", "style", allow_duplicate=True),
    Output("order-header-content", "children", allow_duplicate=True),
    Output("broker-quote-section", "style", allow_duplicate=True),
    Output("broker-quote-content", "children", allow_duplicate=True),
    Output("current-structure", "data", allow_duplicate=True),
    Output("order-input-section", "style", allow_duplicate=True),
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
    noop = ("",) + (no_update,) * 7 + (False,)

    if suppress:
        return noop

    if not underlying or not underlying.strip():
        return noop

    underlying = underlying.strip().upper()
    order_qty_val = int(order_qty) if order_qty else 1

    legs, err_msg = _build_legs_from_table(table_data, underlying, order_qty_val)

    if err_msg:
        return (err_msg,) + (no_update,) * 7 + (False,)

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

    try:
        spot, leg_market, struct_data, multiplier = _fetch_and_price(order)
    except Exception as e:
        return (f"Pricing error: {e}",) + (no_update,) * 7 + (False,)

    new_table = _build_table_data(order, leg_market, struct_data)
    header_style, header_items, broker_style, broker_content, current_data, order_input_style = (
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
        order_input_style,  # order-input-section style
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
def add_order(n_clicks, current_data, existing_orders,
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

    # Persist to JSON
    store_save_orders(orders)

    # Build display rows (strip underscore fields)
    blotter_rows = [
        {k: v for k, v in o.items() if not k.startswith("_")}
        for o in orders
    ]

    return blotter_rows, orders, "", None, None, True


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

    # Persist to JSON
    store_save_orders(updated_orders)

    # Build display rows
    display_rows = [
        {k: v for k, v in o.items() if not k.startswith("_")}
        for o in updated_orders
    ]

    return updated_orders, display_rows, True


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
    visible = [c for c in _BLOTTER_COLUMNS if c["id"] in selected_columns]
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
                style={"color": "#00d4ff", "fontWeight": "bold", "fontSize": "17px"},
            ),
        ]
        header_style = _HEADER_VISIBLE_STYLE
        order_input_style = _ORDER_INPUT_VISIBLE_STYLE

        broker_px = order.get("_broker_price")
        if broker_px and float(broker_px) > 0:
            quote_side = (order.get("_quote_side") or "bid").upper()
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


def main():
    """Run the dashboard."""
    from ..settings import DASHBOARD_DEBUG, DASHBOARD_HOST, DASHBOARD_PORT
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=DASHBOARD_DEBUG)


if __name__ == "__main__":
    main()
