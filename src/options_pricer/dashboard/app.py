"""Dash web app entry point for the IDB options pricer dashboard."""

import plotly.graph_objects as go
from dash import Dash, Input, Output, State, callback, html, no_update

from ..bloomberg import create_client
from ..models import LegMarketData, Side
from ..parser import parse_order
from ..structure_pricer import price_structure_from_market
from .layouts import create_layout

app = Dash(__name__)
app.title = "IDB Options Pricer"
app.layout = create_layout()

# Try live Bloomberg first, fall back to mock
_client = create_client(use_mock=False)


@callback(
    Output("parse-error", "children"),
    Output("order-header", "style"),
    Output("order-header-content", "children"),
    Output("pricing-display", "data"),
    Output("broker-quote-section", "style"),
    Output("broker-quote-content", "children"),
    Output("payoff-graph", "figure"),
    Input("price-btn", "n_clicks"),
    State("order-text", "value"),
    prevent_initial_call=True,
)
def price_order(n_clicks, order_text):
    empty_fig = go.Figure()
    empty_fig.update_layout(template="plotly_dark", height=400)
    hidden = {"display": "none"}

    if not order_text:
        return "Please enter an order.", hidden, [], [], hidden, [], empty_fig

    # Parse the order
    try:
        order = parse_order(order_text)
    except ValueError as e:
        return str(e), hidden, [], [], hidden, [], empty_fig

    # Fetch market data for each leg
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

    # Calculate structure pricing
    struct_data = price_structure_from_market(order, leg_market, spot)

    # --- Build order header ---
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

    header_style = {
        "backgroundColor": "#1a1a2e",
        "padding": "12px 20px",
        "borderRadius": "6px",
        "marginBottom": "15px",
        "display": "block",
    }

    # --- Build pricing table ---
    table_data = []
    base_qty = min(leg.quantity for leg in order.structure.legs) if order.structure.legs else 1

    for leg, mkt in zip(order.structure.legs, leg_market):
        type_str = leg.option_type.value[0].upper()
        exp_str = leg.expiry.strftime("%b%y") if leg.expiry else ""
        label = f"{leg.strike:.0f}{type_str} {exp_str}"

        # Ratio: sell = +, buy = -
        ratio_num = leg.quantity // base_qty
        ratio_str = f"+{ratio_num}" if leg.side == Side.SELL else f"-{ratio_num}"

        mid = (mkt.bid + mkt.offer) / 2.0 if mkt.bid > 0 and mkt.offer > 0 else 0.0
        table_data.append({
            "leg": label,
            "ratio": ratio_str,
            "bid_size": str(mkt.bid_size),
            "bid": f"{mkt.bid:.2f}",
            "mid": f"{mid:.2f}",
            "offer": f"{mkt.offer:.2f}",
            "offer_size": str(mkt.offer_size),
        })

    # Structure row
    table_data.append({
        "leg": "Structure",
        "ratio": "",
        "bid_size": str(struct_data.structure_bid_size),
        "bid": f"{abs(struct_data.structure_bid):.2f}",
        "mid": f"{abs(struct_data.structure_mid):.2f}",
        "offer": f"{abs(struct_data.structure_offer):.2f}",
        "offer_size": str(struct_data.structure_offer_size),
    })

    # --- Broker quote comparison ---
    broker_style = hidden
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
        broker_style = {
            "backgroundColor": "#1a1a2e",
            "padding": "15px 20px",
            "borderRadius": "6px",
            "marginTop": "15px",
            "display": "flex",
            "gap": "20px",
            "alignItems": "center",
        }

    # --- Payoff diagram ---
    structure = order.structure
    strikes = [leg.strike for leg in structure.legs]
    center = sum(strikes) / len(strikes)
    spread = max(strikes) - min(strikes) if len(strikes) > 1 else center * 0.1
    margin = max(spread * 2, center * 0.15)
    low = center - margin
    high = center + margin

    payoff_points = structure.payoff_range(low, high, steps=300)
    spots = [p[0] for p in payoff_points]
    payoffs = [p[1] for p in payoff_points]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=spots, y=payoffs,
        mode="lines",
        name="Payoff at Expiry",
        line=dict(color="#00d4ff", width=2),
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.add_vline(
        x=spot, line_dash="dot", line_color="yellow",
        annotation_text=f"Spot: ${spot:.2f}",
    )
    for s in strikes:
        fig.add_vline(x=s, line_dash="dot", line_color="rgba(255,255,255,0.3)")

    fig.update_layout(
        template="plotly_dark",
        title=f"Payoff Diagram - {order.underlying} {structure.name.upper()}",
        xaxis_title="Underlying Price",
        yaxis_title="P&L per unit",
        height=450,
        margin=dict(l=50, r=30, t=50, b=50),
    )

    return (
        "",
        header_style,
        header_items,
        table_data,
        broker_style,
        broker_content,
        fig,
    )


def main():
    """Run the dashboard."""
    app.run(host="127.0.0.1", port=8050, debug=True)


if __name__ == "__main__":
    main()
