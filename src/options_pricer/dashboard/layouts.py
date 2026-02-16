"""Dashboard layout components for IDB options pricer."""

from dash import dcc, html, dash_table


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
                "Price Structure",
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


def create_pricing_table():
    """Main pricing table: legs + structure row with bid size, bid, mid, offer, offer size."""
    return html.Div(
        className="pricing-table",
        children=[
            dash_table.DataTable(
                id="pricing-display",
                columns=[
                    {"name": "Leg", "id": "leg"},
                    {"name": "Ratio", "id": "ratio"},
                    {"name": "Bid Size", "id": "bid_size"},
                    {"name": "Bid", "id": "bid"},
                    {"name": "Mid", "id": "mid"},
                    {"name": "Offer", "id": "offer"},
                    {"name": "Offer Size", "id": "offer_size"},
                ],
                style_table={"overflowX": "auto"},
                style_cell={
                    "textAlign": "center",
                    "padding": "10px 14px",
                    "fontFamily": "monospace",
                    "fontSize": "14px",
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
                style_data_conditional=[
                    {
                        "if": {"filter_query": '{leg} = "Structure"'},
                        "backgroundColor": "#0f3460",
                        "fontWeight": "bold",
                        "borderTop": "2px solid #00d4ff",
                        "color": "#00d4ff",
                    },
                ],
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


def create_payoff_chart():
    return html.Div(
        className="payoff-chart",
        style={"marginTop": "20px"},
        children=[
            html.H3("Payoff Diagram"),
            dcc.Graph(id="payoff-graph"),
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
            "padding": "20px",
            "maxWidth": "1200px",
            "margin": "0 auto",
        },
        children=[
            create_header(),
            html.Hr(style={"borderColor": "#333"}),
            create_order_input(),
            create_order_header(),
            create_pricing_table(),
            create_broker_quote(),
            html.Hr(style={"borderColor": "#333", "marginTop": "20px"}),
            create_payoff_chart(),
        ],
    )
