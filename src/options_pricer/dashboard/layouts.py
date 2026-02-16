"""Dashboard layout components for IDB options pricer."""

from dash import dcc, html, dash_table

from ..order_store import load_orders

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


# ---------------------------------------------------------------------------
# Order Blotter column definitions
# ---------------------------------------------------------------------------

_BLOTTER_COLUMNS = [
    {"name": "Time", "id": "added_time", "editable": False},
    {"name": "Underlying", "id": "underlying", "editable": False},
    {"name": "Structure", "id": "structure", "editable": False},
    {"name": "Bid", "id": "bid", "editable": False},
    {"name": "Mid", "id": "mid", "editable": False},
    {"name": "Offer", "id": "offer", "editable": False},
    {"name": "Bid Size", "id": "bid_size", "editable": False},
    {"name": "Offer Size", "id": "offer_size", "editable": False},
    {"name": "Bid/Offered", "id": "side", "editable": True, "presentation": "dropdown"},
    {"name": "Size", "id": "size", "editable": True},
    {"name": "Traded", "id": "traded", "editable": True, "presentation": "dropdown"},
    {"name": "Bought/Sold", "id": "bought_sold", "editable": True, "presentation": "dropdown"},
    {"name": "Traded Px", "id": "traded_price", "editable": True},
    {"name": "Initiator", "id": "initiator", "editable": True},
    {"name": "PnL", "id": "pnl", "editable": False},
]

_DEFAULT_VISIBLE = [
    "added_time", "underlying", "structure", "bid", "mid", "offer",
    "side", "size", "traded", "traded_price", "initiator", "pnl",
]

_DEFAULT_HIDDEN = ["bid_size", "offer_size", "bought_sold"]


# ---------------------------------------------------------------------------
# Layout components
# ---------------------------------------------------------------------------

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
                    "boxSizing": "border-box",
                    "padding": "14px",
                    "fontSize": "16px",
                    "fontFamily": "monospace",
                    "backgroundColor": "#1a1a2e",
                    "color": "#00d4ff",
                    "border": "1px solid #333",
                    "borderRadius": "4px",
                    "minHeight": "80px",
                    "resize": "vertical",
                    "lineHeight": "1.5",
                },
            ),
            # Hidden helper to relay Enter keypress from textarea
            dcc.Store(id="textarea-enter", data=0),
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
    """Compact toolbar row with underlying, structure type, order metadata, and Add Order."""
    toolbar_row = html.Div(
        style={
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
                html.Div("Order Price", style=_LABEL_STYLE),
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
                    value=None,
                    placeholder="Side",
                    style={**_DROPDOWN_STYLE, "width": "90px"},
                ),
            ]),
            html.Div([
                html.Div("Qty", style=_LABEL_STYLE),
                dcc.Input(
                    id="manual-quantity", type="number",
                    placeholder="Qty", value=None,
                    style={**_INPUT_STYLE, "width": "80px"},
                ),
            ]),
            html.Div([
                html.Div("\u00a0", style=_LABEL_STYLE),
                html.Button(
                    "Add Order",
                    id="add-order-btn",
                    n_clicks=0,
                    style={
                        "padding": "8px 20px",
                        "backgroundColor": "#198754",
                        "color": "white",
                        "border": "none",
                        "borderRadius": "4px",
                        "cursor": "pointer",
                        "fontSize": "13px",
                        "fontFamily": "monospace",
                    },
                ),
            ]),
        ],
    )
    return html.Div(
        style={
            "backgroundColor": "#1a1a2e",
            "padding": "12px 20px",
            "borderRadius": "6px 6px 0 0",
        },
        children=[
            toolbar_row,
            html.Div(
                id="order-error",
                style={
                    "color": "#ff4444",
                    "fontFamily": "monospace",
                    "fontSize": "13px",
                    "marginTop": "6px",
                },
            ),
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


def create_order_input_section():
    """Hidden stub — preserves IDs that callbacks still output to."""
    return html.Div(
        id="order-input-section",
        style={"display": "none"},
        children=[
            dcc.Dropdown(id="order-side", style={"display": "none"}),
            dcc.Input(id="order-size", type="number", style={"display": "none"}),
        ],
    )


def create_order_blotter(initial_data=None):
    """Order blotter table — library of all priced structures."""
    visible_cols = [c for c in _BLOTTER_COLUMNS if c["id"] in _DEFAULT_VISIBLE]

    return html.Div(
        className="order-blotter",
        style={"marginTop": "20px"},
        children=[
            # Title row with column toggle
            html.Div(
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "10px",
                    "marginBottom": "6px",
                },
                children=[
                    html.H3("Order Blotter", style={"margin": "0"}),
                    html.Button(
                        "Columns",
                        id="column-toggle-btn",
                        n_clicks=0,
                        title="Show/hide blotter columns",
                        style={
                            "padding": "4px 10px",
                            "fontSize": "12px",
                            "backgroundColor": "#333",
                            "color": "#aaa",
                            "border": "1px solid #555",
                            "borderRadius": "4px",
                            "cursor": "pointer",
                        },
                    ),
                ],
            ),
            html.P(
                "Click a row to recall into pricer. Edit cells directly to update order status.",
                style={"color": "#666", "fontSize": "11px", "margin": "0 0 6px 0"},
            ),
            # Column toggle panel (hidden by default)
            html.Div(
                id="column-toggle-panel",
                style={"display": "none"},
                children=[
                    dcc.Checklist(
                        id="column-checklist",
                        options=[
                            {"label": c["name"], "value": c["id"]}
                            for c in _BLOTTER_COLUMNS
                        ],
                        value=_DEFAULT_VISIBLE,
                        style={
                            "display": "flex",
                            "flexWrap": "wrap",
                            "gap": "8px",
                            "padding": "10px",
                            "backgroundColor": "#1a1a2e",
                            "borderRadius": "4px",
                            "fontFamily": "monospace",
                            "fontSize": "12px",
                            "color": "#aaa",
                            "marginBottom": "8px",
                        },
                        inputStyle={"marginRight": "4px"},
                    ),
                ],
            ),
            # Store for visible column IDs
            dcc.Store(id="visible-columns", data=_DEFAULT_VISIBLE),
            # The blotter DataTable
            dash_table.DataTable(
                id="blotter-table",
                columns=visible_cols,
                data=initial_data or [],
                dropdown={
                    "side": {
                        "options": [
                            {"label": "Bid", "value": "Bid"},
                            {"label": "Offered", "value": "Offered"},
                        ],
                    },
                    "traded": {
                        "options": [
                            {"label": "Yes", "value": "Yes"},
                            {"label": "No", "value": "No"},
                        ],
                    },
                    "bought_sold": {
                        "options": [
                            {"label": "Bought", "value": "Bought"},
                            {"label": "Sold", "value": "Sold"},
                            {"label": "-", "value": ""},
                        ],
                    },
                },
                sort_action="native",
                sort_by=[{"column_id": "added_time", "direction": "desc"}],
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
                style_cell_conditional=[
                    # Editable columns get lighter background
                    {
                        "if": {"column_id": [
                            "side", "size", "traded", "bought_sold",
                            "traded_price", "initiator",
                        ]},
                        "backgroundColor": "#1c2a4a",
                    },
                ],
                style_data_conditional=[
                    # Bid/Offered coloring
                    {
                        "if": {
                            "filter_query": '{side} = "Bid"',
                            "column_id": "side",
                        },
                        "color": "#00ff88",
                        "fontWeight": "bold",
                    },
                    {
                        "if": {
                            "filter_query": '{side} = "Offered"',
                            "column_id": "side",
                        },
                        "color": "#ff4444",
                        "fontWeight": "bold",
                    },
                    # Bought/Sold coloring
                    {
                        "if": {
                            "filter_query": '{bought_sold} = "Bought"',
                            "column_id": "bought_sold",
                        },
                        "color": "#00ff88",
                        "fontWeight": "bold",
                    },
                    {
                        "if": {
                            "filter_query": '{bought_sold} = "Sold"',
                            "column_id": "bought_sold",
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
                    # Active row highlight
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
    """Build the full dashboard layout.

    Called by Dash on each page load (app.layout = create_layout) so that
    persisted orders are loaded from JSON on refresh.
    """
    # Load persisted orders from JSON
    orders = load_orders()
    blotter_data = [
        {k: v for k, v in o.items() if not k.startswith("_")}
        for o in orders
    ]

    return html.Div(
        style={
            "fontFamily": "'Segoe UI', Tahoma, sans-serif",
            "backgroundColor": "#0f0f23",
            "color": "#e0e0e0",
            "minHeight": "100vh",
            "padding": "20px 20px 80px 20px",
            "maxWidth": "1400px",
            "margin": "0 auto",
            "boxSizing": "border-box",
        },
        children=[
            # Session data stores
            dcc.Store(id="current-structure", data=None),
            dcc.Store(id="order-store", data=orders),
            dcc.Store(id="suppress-template", data=False),
            dcc.Store(id="auto-price-suppress", data=False),
            dcc.Store(id="blotter-edit-suppress", data=False),
            create_header(),
            html.Hr(style={"borderColor": "#333"}),
            create_order_input(),
            # Toolbar + table grouped as one card
            html.Div(
                style={
                    "backgroundColor": "#16213e",
                    "borderRadius": "8px",
                    "border": "1px solid #333",
                    "overflow": "visible",
                },
                children=[
                    create_pricer_toolbar(),
                    create_pricing_table(),
                ],
            ),
            create_order_header(),
            create_broker_quote(),
            create_order_input_section(),
            html.Hr(style={"borderColor": "#333", "marginTop": "20px"}),
            create_order_blotter(initial_data=blotter_data),
        ],
    )
