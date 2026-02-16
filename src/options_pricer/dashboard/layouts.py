"""Dashboard layout components for IDB options pricer."""

from dash import dcc, html, dash_table

from ..order_store import load_orders

# ---------------------------------------------------------------------------
# Theme palette — refined dark trading terminal
# ---------------------------------------------------------------------------

COLORS = {
    # Backgrounds (layered depth)
    "bg_page": "#0a0e1a",
    "bg_card": "#111827",
    "bg_input": "#1a2236",
    "bg_input_editable": "#1e2a42",
    "bg_active_row": "#1a3352",
    "bg_structure_row": "#0c2d4e",
    "bg_modal_overlay": "rgba(4, 6, 14, 0.92)",
    "bg_hover": "#162033",
    "bg_toolbar": "#131b2e",

    # Text
    "text_primary": "#e2e8f0",
    "text_muted": "#94a3b8",
    "text_hint": "#64748b",
    "text_accent": "#22d3ee",
    "text_heading": "#f1f5f9",

    # Borders
    "border": "#1e293b",
    "border_light": "#334155",
    "border_accent": "rgba(34, 211, 238, 0.15)",
    "border_glow": "rgba(34, 211, 238, 0.25)",

    # Semantic
    "positive": "#34d399",
    "negative": "#f87171",
    "offer_col": "#fb923c",
    "btn_primary": "#0ea5e9",
    "btn_primary_hover": "#0284c7",
    "btn_success": "#059669",
    "btn_danger": "#7f1d1d",
    "btn_danger_border": "#991b1b",
    "btn_neutral": "#1e293b",
    "btn_neutral_border": "#334155",
}

# ---------------------------------------------------------------------------
# Reusable styles
# ---------------------------------------------------------------------------

_FONT_MONO = "'JetBrains Mono', 'Fira Code', 'SF Mono', 'Cascadia Code', Consolas, monospace"
_FONT_SANS = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"

_INPUT_STYLE = {
    "padding": "8px 10px",
    "backgroundColor": COLORS["bg_input"],
    "color": COLORS["text_primary"],
    "border": f"1px solid {COLORS['border_light']}",
    "borderRadius": "6px",
    "fontFamily": _FONT_MONO,
    "fontSize": "13px",
    "outline": "none",
    "transition": "border-color 0.2s ease, box-shadow 0.2s ease",
}

_DROPDOWN_STYLE = {
    "width": "130px",
    "backgroundColor": COLORS["bg_input"],
    "color": COLORS["text_primary"],
    "fontSize": "13px",
    "fontFamily": _FONT_MONO,
}

_LABEL_STYLE = {
    "color": COLORS["text_muted"],
    "fontSize": "11px",
    "fontFamily": _FONT_SANS,
    "fontWeight": "500",
    "letterSpacing": "0.04em",
    "textTransform": "uppercase",
    "marginBottom": "5px",
}

_BTN_BASE = {
    "fontFamily": _FONT_MONO,
    "fontSize": "13px",
    "fontWeight": "500",
    "border": "none",
    "borderRadius": "6px",
    "cursor": "pointer",
    "transition": "all 0.15s ease",
    "letterSpacing": "0.02em",
}

_BTN_NEUTRAL_SM = {
    **_BTN_BASE,
    "padding": "5px 14px",
    "fontSize": "12px",
    "backgroundColor": COLORS["btn_neutral"],
    "color": COLORS["text_muted"],
    "border": f"1px solid {COLORS['btn_neutral_border']}",
}

# CSS rules for DataTable dropdown cells
_TABLE_DROPDOWN_CSS = [
    {
        "selector": ".Select-value-label",
        "rule": f"color: {COLORS['text_primary']} !important; font-family: {_FONT_MONO} !important;",
    },
    {
        "selector": ".Select-placeholder",
        "rule": f"color: {COLORS['text_hint']} !important; font-family: {_FONT_MONO} !important;",
    },
    {
        "selector": ".Select-menu-outer",
        "rule": (
            f"background-color: {COLORS['bg_card']} !important; "
            f"border: 1px solid {COLORS['border_light']} !important; "
            f"border-radius: 6px !important; "
            f"z-index: 9999 !important; "
            f"overflow: visible !important;"
        ),
    },
    {
        "selector": ".Select-option",
        "rule": (
            f"color: {COLORS['text_primary']} !important; "
            f"background-color: {COLORS['bg_card']} !important; "
            f"padding: 8px 12px !important; "
            f"font-family: {_FONT_MONO} !important;"
        ),
    },
    {
        "selector": ".Select-option.is-focused",
        "rule": (
            f"background-color: {COLORS['bg_input']} !important; "
            f"color: {COLORS['text_accent']} !important;"
        ),
    },
    {
        "selector": ".dash-spreadsheet-container",
        "rule": "overflow: visible !important;",
    },
    {
        "selector": ".dash-spreadsheet",
        "rule": "overflow: visible !important;",
    },
    {
        "selector": ".Select-control",
        "rule": (
            f"background-color: {COLORS['bg_input']} !important; "
            f"border-color: {COLORS['border_light']} !important; "
            f"border-radius: 4px !important;"
        ),
    },
    {
        "selector": ".Select-arrow-zone",
        "rule": f"color: {COLORS['text_muted']} !important;",
    },
    {
        "selector": ".dash-cell",
        "rule": "overflow: visible !important;",
    },
]

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


def _to_blotter_rows(orders: list[dict]) -> list[dict]:
    """Convert order store list to display rows (strip _ fields, add delete icon)."""
    return [
        {"delete": "\u2715", **{k: v for k, v in o.items() if not k.startswith("_")}}
        for o in orders
    ]


# ---------------------------------------------------------------------------
# Order Blotter column definitions
# ---------------------------------------------------------------------------

_BLOTTER_COLUMNS = [
    {"name": "", "id": "delete", "editable": False},
    {"name": "Time", "id": "added_time", "editable": False},
    {"name": "User", "id": "created_by", "editable": False},
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
    "delete", "added_time", "created_by", "underlying", "structure", "bid", "mid", "offer",
    "side", "size", "traded", "traded_price", "initiator", "pnl",
]

_DEFAULT_HIDDEN = ["bid_size", "offer_size", "bought_sold"]


# ---------------------------------------------------------------------------
# Google Fonts link tag for web fonts
# ---------------------------------------------------------------------------

def _google_fonts_link():
    """Return a link element to load Inter + JetBrains Mono from Google Fonts."""
    return html.Link(
        rel="stylesheet",
        href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap",
    )


# ---------------------------------------------------------------------------
# Layout components
# ---------------------------------------------------------------------------

_MODAL_OVERLAY_STYLE = {
    "position": "fixed",
    "top": "0",
    "left": "0",
    "width": "100vw",
    "height": "100vh",
    "backgroundColor": COLORS["bg_modal_overlay"],
    "backdropFilter": "blur(8px)",
    "WebkitBackdropFilter": "blur(8px)",
    "display": "flex",
    "justifyContent": "center",
    "alignItems": "center",
    "zIndex": "9999",
}


def create_username_modal():
    """Full-screen blocking modal for username entry on first load."""
    return html.Div(
        id="username-modal",
        style=_MODAL_OVERLAY_STYLE,
        children=[
            html.Div(
                style={
                    "backgroundColor": COLORS["bg_card"],
                    "padding": "48px 44px",
                    "borderRadius": "16px",
                    "border": f"1px solid {COLORS['border_light']}",
                    "boxShadow": "0 25px 50px -12px rgba(0, 0, 0, 0.6), 0 0 40px rgba(34, 211, 238, 0.05)",
                    "textAlign": "center",
                    "maxWidth": "420px",
                    "width": "90%",
                },
                children=[
                    # Logo/icon area
                    html.Div(
                        style={
                            "width": "56px",
                            "height": "56px",
                            "borderRadius": "14px",
                            "background": f"linear-gradient(135deg, {COLORS['btn_primary']}, {COLORS['text_accent']})",
                            "display": "flex",
                            "alignItems": "center",
                            "justifyContent": "center",
                            "margin": "0 auto 24px auto",
                            "fontSize": "24px",
                        },
                        children=html.Span(
                            "\u25C8",
                            style={"color": "white", "lineHeight": "1"},
                        ),
                    ),
                    html.H2(
                        "IDB Options Pricer",
                        style={
                            "color": COLORS["text_heading"],
                            "marginBottom": "6px",
                            "fontFamily": _FONT_SANS,
                            "fontWeight": "600",
                            "fontSize": "22px",
                            "letterSpacing": "-0.02em",
                        },
                    ),
                    html.P(
                        "Enter your name to continue",
                        style={
                            "color": COLORS["text_muted"],
                            "marginBottom": "28px",
                            "fontFamily": _FONT_SANS,
                            "fontSize": "14px",
                            "fontWeight": "400",
                        },
                    ),
                    dcc.Input(
                        id="username-input",
                        type="text",
                        placeholder="Your name",
                        maxLength=20,
                        autoFocus=True,
                        style={
                            **_INPUT_STYLE,
                            "width": "100%",
                            "boxSizing": "border-box",
                            "fontSize": "15px",
                            "padding": "14px 16px",
                            "textAlign": "center",
                            "lineHeight": "1.5",
                            "height": "auto",
                            "borderRadius": "10px",
                            "border": f"1px solid {COLORS['border_light']}",
                        },
                    ),
                    html.Button(
                        "Continue",
                        id="username-submit-btn",
                        n_clicks=0,
                        style={
                            **_BTN_BASE,
                            "marginTop": "16px",
                            "padding": "12px 48px",
                            "fontSize": "15px",
                            "backgroundColor": COLORS["btn_primary"],
                            "color": "white",
                            "width": "100%",
                            "borderRadius": "10px",
                        },
                    ),
                    html.Div(
                        id="username-error",
                        style={
                            "color": COLORS["negative"],
                            "marginTop": "12px",
                            "fontFamily": _FONT_SANS,
                            "fontSize": "13px",
                        },
                    ),
                ],
            ),
        ],
    )


def create_header():
    return html.Div(
        className="header",
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "padding": "4px 0 16px 0",
        },
        children=[
            html.Div([
                html.H1(
                    "IDB Options Pricer",
                    style={
                        "fontFamily": _FONT_SANS,
                        "fontWeight": "700",
                        "fontSize": "26px",
                        "color": COLORS["text_heading"],
                        "margin": "0",
                        "letterSpacing": "-0.03em",
                        "lineHeight": "1.2",
                    },
                ),
                html.P(
                    "Equity Derivatives Structure Pricing",
                    style={
                        "fontFamily": _FONT_SANS,
                        "fontWeight": "400",
                        "fontSize": "13px",
                        "color": COLORS["text_muted"],
                        "margin": "4px 0 0 0",
                        "letterSpacing": "0.02em",
                    },
                ),
            ]),
            html.Div(
                id="user-info",
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "10px",
                    "fontFamily": _FONT_MONO,
                    "fontSize": "13px",
                },
                children=[
                    # Online count pill
                    html.Span(
                        id="online-count",
                        children="0 online",
                        style={
                            "color": COLORS["text_muted"],
                            "fontSize": "12px",
                            "backgroundColor": COLORS["bg_card"],
                            "border": f"1px solid {COLORS['border_light']}",
                            "borderRadius": "12px",
                            "padding": "3px 10px",
                        },
                    ),
                    # Username display
                    html.Span(
                        id="user-display",
                        style={
                            "color": COLORS["text_accent"],
                            "fontWeight": "500",
                        },
                    ),
                    # Change user button
                    html.Button(
                        "\u270E",
                        id="change-user-btn",
                        n_clicks=0,
                        title="Change username",
                        style={
                            **_BTN_BASE,
                            "padding": "2px 7px",
                            "fontSize": "13px",
                            "backgroundColor": "transparent",
                            "color": COLORS["text_hint"],
                            "border": "none",
                            "lineHeight": "1",
                        },
                    ),
                ],
            ),
        ],
    )


def create_order_input():
    return html.Div(
        className="order-input",
        style={"marginBottom": "20px"},
        children=[
            html.Div(
                "PASTE ORDER",
                style={
                    **_LABEL_STYLE,
                    "fontSize": "12px",
                    "marginBottom": "8px",
                },
            ),
            dcc.Textarea(
                id="order-text",
                placeholder='e.g. AAPL Jun26 240/220 PS 1X2 vs250 15d 500x @ 3.50 1X over',
                style={
                    "width": "100%",
                    "boxSizing": "border-box",
                    "padding": "14px 16px",
                    "fontSize": "15px",
                    "fontFamily": _FONT_MONO,
                    "fontWeight": "500",
                    "backgroundColor": COLORS["bg_card"],
                    "color": COLORS["text_accent"],
                    "border": f"1px solid {COLORS['border_light']}",
                    "borderRadius": "10px",
                    "minHeight": "70px",
                    "resize": "vertical",
                    "lineHeight": "1.6",
                    "outline": "none",
                    "transition": "border-color 0.2s ease, box-shadow 0.2s ease",
                },
            ),
            # Hidden helper to relay Enter keypress from textarea
            dcc.Store(id="textarea-enter", data=0),
            html.Div(
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "12px",
                    "marginTop": "10px",
                },
                children=[
                    html.Button(
                        "Parse & Price",
                        id="price-btn",
                        n_clicks=0,
                        style={
                            **_BTN_BASE,
                            "padding": "10px 28px",
                            "fontSize": "14px",
                            "backgroundColor": COLORS["btn_primary"],
                            "color": "white",
                        },
                    ),
                    html.Div(
                        id="parse-error",
                        style={
                            "color": COLORS["negative"],
                            "fontFamily": _FONT_MONO,
                            "fontSize": "13px",
                        },
                    ),
                ],
            ),
        ],
    )


def create_pricer_toolbar():
    """Compact toolbar row with underlying, structure type, order metadata, and Add Order."""
    toolbar_row = html.Div(
        style={
            "display": "flex",
            "gap": "12px",
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
                    style={**_DROPDOWN_STYLE, "width": "100px"},
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
                        **_BTN_BASE,
                        "padding": "8px 22px",
                        "backgroundColor": COLORS["btn_success"],
                        "color": "white",
                    },
                ),
            ]),
        ],
    )
    return html.Div(
        style={
            "backgroundColor": COLORS["bg_toolbar"],
            "padding": "14px 20px",
            "borderRadius": "10px 10px 0 0",
            "borderBottom": f"1px solid {COLORS['border']}",
        },
        children=[
            toolbar_row,
            html.Div(
                id="order-error",
                style={
                    "color": COLORS["negative"],
                    "fontFamily": _FONT_MONO,
                    "fontSize": "13px",
                    "marginTop": "6px",
                },
            ),
        ],
    )


def create_pricing_table():
    """Unified editable pricing table -- input columns + output columns."""
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
                css=_TABLE_DROPDOWN_CSS,
                style_table={
                    "overflowX": "auto",
                    "overflowY": "visible",
                },
                style_cell={
                    "textAlign": "center",
                    "padding": "10px 12px",
                    "fontFamily": _FONT_MONO,
                    "fontSize": "13px",
                    "border": "none",
                    "overflow": "visible",
                },
                style_header={
                    "backgroundColor": COLORS["bg_toolbar"],
                    "color": COLORS["text_muted"],
                    "fontFamily": _FONT_SANS,
                    "fontWeight": "600",
                    "fontSize": "11px",
                    "letterSpacing": "0.05em",
                    "textTransform": "uppercase",
                    "borderBottom": f"1px solid {COLORS['border_light']}",
                    "padding": "10px 12px",
                },
                style_data={
                    "backgroundColor": COLORS["bg_input"],
                    "color": COLORS["text_primary"],
                    "borderBottom": f"1px solid {COLORS['border']}",
                },
                style_cell_conditional=[
                    # Editable columns get a slightly lighter background
                    {
                        "if": {"column_id": ["expiry", "strike", "type", "side", "qty"]},
                        "backgroundColor": COLORS["bg_input_editable"],
                    },
                    # Leg column narrower
                    {"if": {"column_id": "leg"}, "width": "70px"},
                    {"if": {"column_id": "expiry"}, "width": "80px"},
                    {"if": {"column_id": "qty"}, "width": "50px"},
                ],
                style_data_conditional=[
                    # Color-coded pricing columns
                    {"if": {"column_id": "bid"}, "color": COLORS["positive"]},
                    {"if": {"column_id": "offer"}, "color": COLORS["offer_col"]},
                    # Structure summary row (last -- overrides column colors)
                    {
                        "if": {"filter_query": '{leg} = "Structure"'},
                        "backgroundColor": COLORS["bg_structure_row"],
                        "fontWeight": "700",
                        "borderTop": f"2px solid {COLORS['text_accent']}",
                        "color": COLORS["text_accent"],
                    },
                ],
            ),
            # Action row below table
            html.Div(
                style={
                    "display": "flex",
                    "gap": "8px",
                    "alignItems": "center",
                    "padding": "12px 16px",
                    "flexWrap": "wrap",
                },
                children=[
                    html.Button(
                        "+ Row", id="add-row-btn", n_clicks=0,
                        style=_BTN_NEUTRAL_SM,
                    ),
                    html.Button(
                        "- Row", id="remove-row-btn", n_clicks=0,
                        style=_BTN_NEUTRAL_SM,
                    ),
                    html.Button(
                        "Clear", id="clear-btn", n_clicks=0,
                        style={
                            **_BTN_BASE,
                            "padding": "5px 14px",
                            "fontSize": "12px",
                            "backgroundColor": COLORS["btn_danger"],
                            "color": COLORS["text_primary"],
                            "border": f"1px solid {COLORS['btn_danger_border']}",
                            "marginLeft": "8px",
                        },
                    ),
                    html.Div(
                        id="table-error",
                        style={
                            "color": COLORS["negative"],
                            "fontFamily": _FONT_MONO,
                            "fontSize": "13px",
                        },
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
            "backgroundColor": COLORS["bg_card"],
            "padding": "14px 20px",
            "borderRadius": "10px",
            "marginBottom": "14px",
            "border": f"1px solid {COLORS['border_accent']}",
            "display": "none",
        },
        children=[
            html.Div(
                id="order-header-content",
                style={
                    "display": "flex",
                    "gap": "28px",
                    "fontSize": "14px",
                    "fontFamily": _FONT_MONO,
                    "flexWrap": "wrap",
                    "alignItems": "center",
                },
            ),
        ],
    )


def create_broker_quote():
    """Display broker's quoted price vs screen market."""
    return html.Div(
        id="broker-quote-section",
        style={
            "backgroundColor": COLORS["bg_card"],
            "padding": "14px 20px",
            "borderRadius": "10px",
            "marginTop": "14px",
            "border": f"1px solid {COLORS['border']}",
            "display": "none",
        },
        children=[
            html.Div(
                id="broker-quote-content",
                style={"fontFamily": _FONT_MONO},
            ),
        ],
    )


def create_order_input_section():
    """Hidden stub -- preserves IDs that callbacks still output to."""
    return html.Div(
        id="order-input-section",
        style={"display": "none"},
        children=[
            dcc.Dropdown(id="order-side", style={"display": "none"}),
            dcc.Input(id="order-size", type="number", style={"display": "none"}),
        ],
    )


def create_order_blotter(initial_data=None):
    """Order blotter table -- library of all priced structures."""
    visible_cols = [c for c in _BLOTTER_COLUMNS if c["id"] in _DEFAULT_VISIBLE]

    return html.Div(
        className="order-blotter",
        style={"marginTop": "24px"},
        children=[
            # Title row with column toggle
            html.Div(
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "12px",
                    "marginBottom": "8px",
                },
                children=[
                    html.H3(
                        "Order Blotter",
                        style={
                            "margin": "0",
                            "fontFamily": _FONT_SANS,
                            "fontWeight": "600",
                            "fontSize": "18px",
                            "color": COLORS["text_heading"],
                            "letterSpacing": "-0.02em",
                        },
                    ),
                    html.Button(
                        "Columns",
                        id="column-toggle-btn",
                        n_clicks=0,
                        title="Show/hide blotter columns",
                        style={
                            **_BTN_BASE,
                            "padding": "4px 12px",
                            "fontSize": "11px",
                            "backgroundColor": COLORS["btn_neutral"],
                            "color": COLORS["text_muted"],
                            "border": f"1px solid {COLORS['btn_neutral_border']}",
                        },
                    ),
                ],
            ),
            html.P(
                "Click a row to recall into pricer. Edit cells directly to update order status.",
                style={
                    "color": COLORS["text_hint"],
                    "fontSize": "12px",
                    "fontFamily": _FONT_SANS,
                    "margin": "0 0 10px 0",
                },
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
                            if c["id"] != "delete"
                        ],
                        value=_DEFAULT_VISIBLE,
                        style={
                            "display": "flex",
                            "flexWrap": "wrap",
                            "gap": "10px",
                            "padding": "12px 14px",
                            "backgroundColor": COLORS["bg_card"],
                            "borderRadius": "8px",
                            "border": f"1px solid {COLORS['border']}",
                            "fontFamily": _FONT_MONO,
                            "fontSize": "12px",
                            "color": COLORS["text_muted"],
                            "marginBottom": "10px",
                        },
                        inputStyle={"marginRight": "5px"},
                    ),
                ],
            ),
            # Store for visible column IDs
            dcc.Store(id="visible-columns", data=_DEFAULT_VISIBLE),
            # Store for pending delete order ID
            dcc.Store(id="pending-delete-id", data=None),
            # Delete confirmation modal
            html.Div(
                id="delete-confirm-modal",
                style={"display": "none"},
                children=[
                    html.Div(
                        style={
                            "position": "fixed",
                            "top": "0",
                            "left": "0",
                            "width": "100vw",
                            "height": "100vh",
                            "backgroundColor": COLORS["bg_modal_overlay"],
                            "backdropFilter": "blur(4px)",
                            "WebkitBackdropFilter": "blur(4px)",
                            "display": "flex",
                            "justifyContent": "center",
                            "alignItems": "center",
                            "zIndex": "9998",
                        },
                        children=[
                            html.Div(
                                style={
                                    "backgroundColor": COLORS["bg_card"],
                                    "padding": "32px 36px",
                                    "borderRadius": "12px",
                                    "border": f"1px solid {COLORS['btn_danger_border']}",
                                    "boxShadow": "0 25px 50px -12px rgba(0, 0, 0, 0.6)",
                                    "textAlign": "center",
                                    "maxWidth": "380px",
                                    "width": "90%",
                                },
                                children=[
                                    html.Div(
                                        "Delete Order",
                                        style={
                                            "color": COLORS["negative"],
                                            "fontFamily": _FONT_SANS,
                                            "fontWeight": "600",
                                            "fontSize": "18px",
                                            "marginBottom": "8px",
                                        },
                                    ),
                                    html.Div(
                                        id="delete-confirm-detail",
                                        style={
                                            "color": COLORS["text_muted"],
                                            "fontFamily": _FONT_MONO,
                                            "fontSize": "13px",
                                            "marginBottom": "24px",
                                            "lineHeight": "1.5",
                                        },
                                    ),
                                    html.Div(
                                        style={
                                            "display": "flex",
                                            "gap": "10px",
                                            "justifyContent": "center",
                                        },
                                        children=[
                                            html.Button(
                                                "Cancel",
                                                id="delete-cancel-btn",
                                                n_clicks=0,
                                                style={
                                                    **_BTN_BASE,
                                                    "padding": "10px 28px",
                                                    "fontSize": "14px",
                                                    "backgroundColor": COLORS["btn_neutral"],
                                                    "color": COLORS["text_muted"],
                                                    "border": f"1px solid {COLORS['btn_neutral_border']}",
                                                },
                                            ),
                                            html.Button(
                                                "Delete",
                                                id="delete-confirm-btn",
                                                n_clicks=0,
                                                style={
                                                    **_BTN_BASE,
                                                    "padding": "10px 28px",
                                                    "fontSize": "14px",
                                                    "backgroundColor": COLORS["btn_danger"],
                                                    "color": COLORS["text_primary"],
                                                    "border": f"1px solid {COLORS['btn_danger_border']}",
                                                },
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
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
                css=_TABLE_DROPDOWN_CSS,
                style_table={
                    "overflowX": "auto",
                    "overflowY": "visible",
                    "borderRadius": "10px",
                    "border": f"1px solid {COLORS['border']}",
                },
                style_cell={
                    "textAlign": "center",
                    "padding": "10px 14px",
                    "fontFamily": _FONT_MONO,
                    "fontSize": "13px",
                    "cursor": "pointer",
                    "border": "none",
                    "overflow": "visible",
                    "whiteSpace": "normal",
                    "minWidth": "60px",
                },
                style_header={
                    "backgroundColor": COLORS["bg_toolbar"],
                    "color": COLORS["text_muted"],
                    "fontFamily": _FONT_SANS,
                    "fontWeight": "600",
                    "fontSize": "11px",
                    "letterSpacing": "0.05em",
                    "textTransform": "uppercase",
                    "borderBottom": f"1px solid {COLORS['border_light']}",
                    "padding": "11px 14px",
                    "cursor": "default",
                },
                style_data={
                    "backgroundColor": COLORS["bg_input"],
                    "color": COLORS["text_primary"],
                    "borderBottom": f"1px solid {COLORS['border']}",
                },
                style_cell_conditional=[
                    # Delete column: narrow, no-sort icon
                    {
                        "if": {"column_id": "delete"},
                        "width": "36px",
                        "minWidth": "36px",
                        "maxWidth": "36px",
                        "padding": "0",
                        "cursor": "pointer",
                    },
                    # Editable columns get lighter background
                    {
                        "if": {"column_id": [
                            "side", "size", "traded", "bought_sold",
                            "traded_price", "initiator",
                        ]},
                        "backgroundColor": COLORS["bg_input_editable"],
                    },
                    # Structure column wider to prevent text clipping
                    {"if": {"column_id": "structure"}, "minWidth": "160px", "whiteSpace": "normal"},
                ],
                style_data_conditional=[
                    # Bid/Offered coloring
                    {
                        "if": {
                            "filter_query": '{side} = "Bid"',
                            "column_id": "side",
                        },
                        "color": COLORS["positive"],
                        "fontWeight": "600",
                    },
                    {
                        "if": {
                            "filter_query": '{side} = "Offered"',
                            "column_id": "side",
                        },
                        "color": COLORS["negative"],
                        "fontWeight": "600",
                    },
                    # Bought/Sold coloring
                    {
                        "if": {
                            "filter_query": '{bought_sold} = "Bought"',
                            "column_id": "bought_sold",
                        },
                        "color": COLORS["positive"],
                        "fontWeight": "600",
                    },
                    {
                        "if": {
                            "filter_query": '{bought_sold} = "Sold"',
                            "column_id": "bought_sold",
                        },
                        "color": COLORS["negative"],
                        "fontWeight": "600",
                    },
                    # PnL coloring
                    {
                        "if": {
                            "filter_query": '{pnl} contains "-"',
                            "column_id": "pnl",
                        },
                        "color": COLORS["negative"],
                        "fontWeight": "600",
                    },
                    {
                        "if": {
                            "filter_query": '{pnl} contains "+"',
                            "column_id": "pnl",
                        },
                        "color": COLORS["positive"],
                        "fontWeight": "600",
                    },
                    # Delete column styling
                    {
                        "if": {"column_id": "delete"},
                        "color": COLORS["text_hint"],
                        "fontSize": "15px",
                    },
                    # Active row highlight
                    {
                        "if": {"state": "active"},
                        "backgroundColor": COLORS["bg_active_row"],
                        "border": f"1px solid {COLORS['border_glow']}",
                    },
                ],
            ),
        ],
    )


def create_layout():
    """Build the full dashboard layout.

    Called by Dash on each page load (app.layout = create_layout) so that
    persisted orders are loaded from SQLite on refresh.
    """
    # Load persisted orders from SQLite
    orders = load_orders()
    blotter_data = _to_blotter_rows(orders)

    return html.Div(
        style={
            "fontFamily": _FONT_SANS,
            "backgroundColor": COLORS["bg_page"],
            "color": COLORS["text_primary"],
            "minHeight": "100vh",
            "padding": "24px 28px 80px 28px",
            "width": "100%",
            "boxSizing": "border-box",
        },
        children=[
            # Load web fonts
            _google_fonts_link(),
            # Username modal (blocking overlay until name entered)
            create_username_modal(),
            # Session data stores
            dcc.Store(id="current-structure", data=None),
            dcc.Store(id="order-store", data=orders),
            dcc.Store(id="suppress-template", data=False),
            dcc.Store(id="auto-price-suppress", data=False),
            dcc.Store(id="blotter-edit-suppress", data=False),
            # Multi-user stores
            dcc.Store(id="current-user", storage_type="session", data=""),
            dcc.Store(id="ws-blotter-refresh", data=0),
            dcc.Store(id="ws-online-count", data=0),
            # Fallback polling interval for blotter sync (every 5s)
            dcc.Interval(id="blotter-poll", interval=5000, n_intervals=0),
            create_header(),
            # Subtle divider
            html.Div(
                style={
                    "height": "1px",
                    "background": f"linear-gradient(90deg, transparent, {COLORS['border_light']}, transparent)",
                    "margin": "0 0 20px 0",
                },
            ),
            create_order_input(),
            # Toolbar + table grouped as one card
            html.Div(
                style={
                    "backgroundColor": COLORS["bg_input"],
                    "borderRadius": "10px",
                    "border": f"1px solid {COLORS['border']}",
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
            # Subtle divider
            html.Div(
                style={
                    "height": "1px",
                    "background": f"linear-gradient(90deg, transparent, {COLORS['border_light']}, transparent)",
                    "margin": "24px 0 0 0",
                },
            ),
            create_order_blotter(initial_data=blotter_data),
        ],
    )
