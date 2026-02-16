"""Dashboard layout components for IDB options pricer."""

from dash import dcc, html, dash_table

# Reusable styles
_INPUT_STYLE = {
    "padding": "8px",
    "backgroundColor": "#16213e",
    "color": "#e0e0e0",
    "border": "1px solid #333",
    "borderRadius": "4px",
    "fontFamily": "monospace",
    "fontSize": "13px",
}

_DROPDOWN_STYLE = {
    "width": "110px",
    "backgroundColor": "#16213e",
    "color": "#000",
    "fontSize": "13px",
}

_LABEL_STYLE = {"color": "#aaa", "fontSize": "12px", "marginBottom": "4px"}

STRUCTURE_TYPE_OPTIONS = [
    {"label": "Single", "value": "single"},
    {"label": "Put Spread", "value": "put_spread"},
    {"label": "Call Spread", "value": "call_spread"},
    {"label": "Risk Reversal", "value": "risk_reversal"},
    {"label": "Straddle", "value": "straddle"},
    {"label": "Strangle", "value": "strangle"},
    {"label": "Butterfly", "value": "butterfly"},
    {"label": "Iron Condor", "value": "iron_condor"},
    {"label": "Collar", "value": "collar"},
]

# Empty leg row template
_EMPTY_ROW = {
    "leg": "", "expiry": "", "strike": "", "type": "", "side": "",
    "qty": 1, "bid_size": "", "bid": "", "mid": "", "offer": "", "offer_size": "",
}


def _make_empty_rows(n: int = 2) -> list[dict]:
    """Create n empty leg rows with Leg labels."""
    return [{**_EMPTY_ROW, "leg": f"Leg {i + 1}"} for i in range(n)]


def create_header():
    return html.Div(
        className="header",
        children=[
            html.H1("IDB Options Pricer"),
            html.P("Equity Derivatives Structure Pricing Tool"),
        ],
    )


def create_order_input():
    return html.Div(
        className="order-input",
        style={"marginBottom": "20px"},
        children=[
            html.H3("Paste Order"),
            dcc.Textarea(
                id="order-text",
                placeholder='e.g. AAPL Jun26 240/220 PS 1X2 vs250 15d 500x @ 3.50 1X over',
                style={
                    "width": "100%",
                    "padding": "14px",
                    "fontSize": "16px",
                    "fontFamily": "monospace",
                    "backgroundColor": "#1a1a2e",
                    "color": "#00d4ff",
                    "border": "1px solid #333",
                    "borderRadius": "4px",
                    "resize": "vertical",
                    "minHeight": "50px",
                },
            ),
            html.Button(
                "Parse & Price",
                id="price-btn",
                n_clicks=0,
                style={
                    "marginTop": "10px",
                    "padding": "10px 30px",
                    "fontSize": "16px",
                    "backgroundColor": "#0d6efd",
                    "color": "white",
                    "border": "none",
                    "borderRadius": "4px",
                    "cursor": "pointer",
                },
            ),
            html.Div(id="parse-error", style={"color": "#ff4444", "marginTop": "8px"}),
        ],
    )


def create_pricer_toolbar():
    """Compact toolbar row with underlying, structure type, and order metadata."""
    return html.Div(
        style={
            "backgroundColor": "#1a1a2e",
            "padding": "12px 20px",
            "borderRadius": "6px 6px 0 0",
            "display": "flex",
            "gap": "15px",
            "alignItems": "flex-end",
            "flexWrap": "wrap",
        },
        children=[
            html.Div([
                html.Div("Underlying", style=_LABEL_STYLE),
                dcc.Input(
                    id="manual-underlying", type="text",
                    placeholder="e.g. AAPL", debounce=True,
                    style={**_INPUT_STYLE, "width": "100px", "textTransform": "uppercase"},
                ),
            ]),
            html.Div([
                html.Div("Structure", style=_LABEL_STYLE),
                dcc.Dropdown(
                    id="manual-structure-type",
                    options=STRUCTURE_TYPE_OPTIONS,
                    placeholder="Select...",
                    style={**_DROPDOWN_STYLE, "width": "160px"},
                ),
            ]),
            html.Div([
                html.Div("Tie", style=_LABEL_STYLE),
                dcc.Input(
                    id="manual-stock-ref", type="number",
                    placeholder="0.00",
                    style={**_INPUT_STYLE, "width": "90px"},
                ),
            ]),
            html.Div([
                html.Div("Delta", style=_LABEL_STYLE),
                dcc.Input(
                    id="manual-delta", type="number",
                    placeholder="0",
                    style={**_INPUT_STYLE, "width": "70px"},
                ),
            ]),
            html.Div([
                html.Div("Broker Px", style=_LABEL_STYLE),
                dcc.Input(
                    id="manual-broker-price", type="number",
                    placeholder="0.00",
                    style={**_INPUT_STYLE, "width": "90px"},
                ),
            ]),
            html.Div([
                html.Div("Side", style=_LABEL_STYLE),
                dcc.Dropdown(
                    id="manual-quote-side",
                    options=[
                        {"label": "Bid", "value": "bid"},
                        {"label": "Offer", "value": "offer"},
                    ],
                    value="bid",
                    style={**_DROPDOWN_STYLE, "width": "90px"},
                ),
            ]),
            html.Div([
                html.Div("Qty", style=_LABEL_STYLE),
                dcc.Input(
                    id="manual-quantity", type="number",
                    placeholder="100", value=100, min=1,
                    style={**_INPUT_STYLE, "width": "80px"},
                ),
            ]),
        ],
    )


def create_pricing_table():
    """Unified editable pricing table — input columns + output columns."""
    return html.Div(
        className="pricing-table",
        children=[
            dash_table.DataTable(
                id="pricing-display",
                columns=[
                    {"name": "Leg", "id": "leg", "editable": False},
                    {"name": "Expiry", "id": "expiry", "editable": True},
                    {"name": "Strike", "id": "strike", "editable": True, "type": "numeric"},
                    {"name": "Type", "id": "type", "editable": True, "presentation": "dropdown"},
                    {"name": "Side", "id": "side", "editable": True, "presentation": "dropdown"},
                    {"name": "Qty", "id": "qty", "editable": True, "type": "numeric"},
                    {"name": "Bid Size", "id": "bid_size", "editable": False},
                    {"name": "Bid", "id": "bid", "editable": False},
                    {"name": "Mid", "id": "mid", "editable": False},
                    {"name": "Offer", "id": "offer", "editable": False},
                    {"name": "Offer Size", "id": "offer_size", "editable": False},
                ],
                data=_make_empty_rows(2),
                dropdown={
                    "type": {
                        "options": [
                            {"label": "Call", "value": "C"},
                            {"label": "Put", "value": "P"},
                        ],
                    },
                    "side": {
                        "options": [
                            {"label": "Buy", "value": "B"},
                            {"label": "Sell", "value": "S"},
                        ],
                    },
                },
                style_table={"overflowX": "auto"},
                style_cell={
                    "textAlign": "center",
                    "padding": "8px 10px",
                    "fontFamily": "monospace",
                    "fontSize": "13px",
                },
                style_header={
                    "backgroundColor": "#1a1a2e",
                    "color": "#aaa",
                    "fontWeight": "bold",
                    "borderBottom": "2px solid #333",
                },
                style_data={
                    "backgroundColor": "#16213e",
                    "color": "#e0e0e0",
                    "borderBottom": "1px solid #1a1a2e",
                },
                style_cell_conditional=[
                    # Input columns get a slightly lighter background
                    {
                        "if": {"column_id": ["expiry", "strike", "type", "side", "qty"]},
                        "backgroundColor": "#1c2a4a",
                    },
                    # Leg column narrower
                    {"if": {"column_id": "leg"}, "width": "70px"},
                    {"if": {"column_id": "expiry"}, "width": "80px"},
                    {"if": {"column_id": "qty"}, "width": "50px"},
                ],
                style_data_conditional=[
                    # Color-coded pricing columns
                    {"if": {"column_id": "bid"}, "color": "#00ff88"},
                    {"if": {"column_id": "offer"}, "color": "#ff6b6b"},
                    # Structure summary row (last — overrides column colors)
                    {
                        "if": {"filter_query": '{leg} = "Structure"'},
                        "backgroundColor": "#0f3460",
                        "fontWeight": "bold",
                        "borderTop": "2px solid #00d4ff",
                        "color": "#00d4ff",
                    },
                ],
            ),
            # Action row below table
            html.Div(
                style={
                    "display": "flex",
                    "gap": "10px",
                    "alignItems": "center",
                    "marginTop": "10px",
                    "flexWrap": "wrap",
                },
                children=[
                    html.Button(
                        "+ Row", id="add-row-btn", n_clicks=0,
                        style={
                            "padding": "4px 14px", "fontSize": "12px",
                            "backgroundColor": "#333", "color": "#aaa",
                            "border": "1px solid #555", "borderRadius": "4px",
                            "cursor": "pointer",
                        },
                    ),
                    html.Button(
                        "- Row", id="remove-row-btn", n_clicks=0,
                        style={
                            "padding": "4px 14px", "fontSize": "12px",
                            "backgroundColor": "#333", "color": "#aaa",
                            "border": "1px solid #555", "borderRadius": "4px",
                            "cursor": "pointer",
                        },
                    ),
                    html.Button(
                        "Clear", id="clear-btn", n_clicks=0,
                        style={
                            "padding": "4px 14px", "fontSize": "12px",
                            "backgroundColor": "#8b0000", "color": "#e0e0e0",
                            "border": "1px solid #aa3333", "borderRadius": "4px",
                            "cursor": "pointer", "marginLeft": "10px",
                        },
                    ),
                    html.Div(
                        id="table-error",
                        style={"color": "#ff4444", "fontFamily": "monospace", "fontSize": "13px"},
                    ),
                ],
            ),
        ],
    )


def create_order_header():
    """Header bar showing parsed order info: ticker, structure, tie, stock, delta."""
    return html.Div(
        id="order-header",
        style={
            "backgroundColor": "#1a1a2e",
            "padding": "12px 20px",
            "borderRadius": "6px",
            "marginBottom": "15px",
            "display": "none",
        },
        children=[
            html.Div(
                id="order-header-content",
                style={
                    "display": "flex",
                    "gap": "30px",
                    "fontSize": "15px",
                    "fontFamily": "monospace",
                    "flexWrap": "wrap",
                },
            ),
        ],
    )


def create_broker_quote():
    """Display broker's quoted price vs screen market."""
    return html.Div(
        id="broker-quote-section",
        style={
            "backgroundColor": "#1a1a2e",
            "padding": "15px 20px",
            "borderRadius": "6px",
            "marginTop": "15px",
            "display": "none",
        },
        children=[
            html.Div(id="broker-quote-content", style={"fontFamily": "monospace"}),
        ],
    )


def create_trade_input():
    """Trade input row: buyer/seller, traded price, size, add button."""
    return html.Div(
        id="trade-input-section",
        style={
            "backgroundColor": "#1a1a2e",
            "padding": "15px 20px",
            "borderRadius": "6px",
            "marginTop": "15px",
            "display": "none",
        },
        children=[
            html.Div(
                style={
                    "display": "flex",
                    "gap": "15px",
                    "alignItems": "center",
                    "flexWrap": "wrap",
                    "fontFamily": "monospace",
                },
                children=[
                    html.Label("Add Trade:", style={"fontWeight": "bold", "color": "#aaa"}),
                    dcc.Dropdown(
                        id="trade-side",
                        options=[
                            {"label": "Buyer", "value": "Buyer"},
                            {"label": "Seller", "value": "Seller"},
                        ],
                        placeholder="B/S",
                        style={
                            "width": "120px",
                            "backgroundColor": "#16213e",
                            "color": "#000",
                        },
                    ),
                    dcc.Input(
                        id="trade-price",
                        type="number",
                        placeholder="Traded Price",
                        style={
                            "width": "130px",
                            "padding": "8px",
                            "backgroundColor": "#16213e",
                            "color": "#e0e0e0",
                            "border": "1px solid #333",
                            "borderRadius": "4px",
                        },
                    ),
                    dcc.Input(
                        id="trade-size",
                        type="number",
                        placeholder="Size",
                        style={
                            "width": "100px",
                            "padding": "8px",
                            "backgroundColor": "#16213e",
                            "color": "#e0e0e0",
                            "border": "1px solid #333",
                            "borderRadius": "4px",
                        },
                    ),
                    html.Button(
                        "Add Trade",
                        id="add-trade-btn",
                        n_clicks=0,
                        style={
                            "padding": "8px 20px",
                            "backgroundColor": "#198754",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "4px",
                            "cursor": "pointer",
                            "fontSize": "14px",
                        },
                    ),
                    html.Div(id="trade-error", style={"color": "#ff4444"}),
                ],
            ),
        ],
    )


def create_trade_blotter():
    """Trade blotter table showing all trades for the day."""
    return html.Div(
        className="trade-blotter",
        style={"marginTop": "20px"},
        children=[
            html.H3("Trade Blotter"),
            html.P(
                "Click a row to recall into pricer",
                style={"color": "#666", "fontSize": "11px", "margin": "0 0 6px 0"},
            ),
            dash_table.DataTable(
                id="blotter-table",
                columns=[
                    {"name": "Time", "id": "added_time"},
                    {"name": "Underlying", "id": "underlying"},
                    {"name": "Structure", "id": "structure"},
                    {"name": "Bid Size", "id": "bid_size"},
                    {"name": "Bid", "id": "bid"},
                    {"name": "Mid", "id": "mid"},
                    {"name": "Offer", "id": "offer"},
                    {"name": "Offer Size", "id": "offer_size"},
                    {"name": "B/S", "id": "buyer_seller"},
                    {"name": "Traded", "id": "traded_price"},
                    {"name": "Size", "id": "size"},
                    {"name": "PnL", "id": "pnl"},
                ],
                data=[],
                style_table={"overflowX": "auto"},
                style_cell={
                    "textAlign": "center",
                    "padding": "10px 14px",
                    "fontFamily": "monospace",
                    "fontSize": "13px",
                    "cursor": "pointer",
                },
                style_header={
                    "backgroundColor": "#1a1a2e",
                    "color": "#aaa",
                    "fontWeight": "bold",
                    "borderBottom": "2px solid #333",
                    "cursor": "default",
                },
                style_data={
                    "backgroundColor": "#16213e",
                    "color": "#e0e0e0",
                    "borderBottom": "1px solid #1a1a2e",
                },
                style_data_conditional=[
                    # B/S font coloring
                    {
                        "if": {
                            "filter_query": '{buyer_seller} = "Buyer"',
                            "column_id": "buyer_seller",
                        },
                        "color": "#00ff88",
                        "fontWeight": "bold",
                    },
                    {
                        "if": {
                            "filter_query": '{buyer_seller} = "Seller"',
                            "column_id": "buyer_seller",
                        },
                        "color": "#ff4444",
                        "fontWeight": "bold",
                    },
                    # PnL coloring
                    {
                        "if": {
                            "filter_query": "{pnl} contains '-'",
                            "column_id": "pnl",
                        },
                        "color": "#ff4444",
                        "fontWeight": "bold",
                    },
                    {
                        "if": {
                            "filter_query": "{pnl} contains '+'",
                            "column_id": "pnl",
                        },
                        "color": "#00ff88",
                        "fontWeight": "bold",
                    },
                    {
                        "if": {"state": "active"},
                        "backgroundColor": "#1a3a5e",
                        "border": "1px solid #00d4ff",
                    },
                ],
            ),
        ],
    )


def create_layout():
    """Build the full dashboard layout."""
    return html.Div(
        style={
            "fontFamily": "'Segoe UI', Tahoma, sans-serif",
            "backgroundColor": "#0f0f23",
            "color": "#e0e0e0",
            "minHeight": "100vh",
            "padding": "20px 20px 80px 20px",
            "maxWidth": "1200px",
            "margin": "0 auto",
        },
        children=[
            # Session data stores
            dcc.Store(id="current-structure", data=None),
            dcc.Store(id="trade-store", data=[]),
            dcc.Store(id="suppress-template", data=False),
            dcc.Store(id="auto-price-suppress", data=False),
            create_header(),
            html.Hr(style={"borderColor": "#333"}),
            create_order_input(),
            # Toolbar + table grouped as one card
            html.Div(
                style={
                    "backgroundColor": "#16213e",
                    "borderRadius": "8px",
                    "border": "1px solid #333",
                    "overflow": "hidden",
                },
                children=[
                    create_pricer_toolbar(),
                    create_pricing_table(),
                ],
            ),
            create_order_header(),
            create_broker_quote(),
            create_trade_input(),
            html.Hr(style={"borderColor": "#333", "marginTop": "20px"}),
            create_trade_blotter(),
        ],
    )
