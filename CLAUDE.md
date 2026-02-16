# Options Pricer — Project Context

## What This Is
An options pricing tool for an IDB (inter-dealer broker) equity derivatives broker. Parses real broker shorthand orders, fetches screen market data (Bloomberg or mock), and displays structure-level implied bid/offer/mid on a web dashboard.

The core use case: broker sends an order like `AAPL Jun26 240/220 PS 1X2 vs250 15d 500x @ 3.50 1X over`, user pastes it into the dashboard, and instantly sees screen-implied pricing for the structure to compare against the broker's quote.

## Tech Stack
- **Python 3.12** (venv at `.venv/`, activate with `source .venv/Scripts/activate` on Windows)
- **Dash (Plotly)** — web dashboard
- **NumPy / SciPy** — numerical pricing
- **blpapi 3.25.12** — Bloomberg Terminal API (installed; falls back to mock when Terminal not running)
- **Flask-SocketIO** — WebSocket server for multi-user live blotter sync
- **pytest** — 106 tests, all passing

## Project Structure
```
src/options_pricer/
├── models.py            # OptionLeg, OptionStructure, ParsedOrder, LegMarketData, StructureMarketData
├── parser.py            # Flexible IDB broker shorthand parser (regex-based, order-independent tokens)
├── pricer.py            # Black-Scholes pricing engine + Greeks (delta, gamma, theta, vega, rho)
├── structure_pricer.py  # Calculates structure bid/offer/mid from individual leg screen prices
├── bloomberg.py         # BloombergClient (live) + MockBloombergClient (BS-based realistic quotes)
├── order_store.py       # SQLite persistence for orders (~/.options_pricer/orders.db)
├── settings.py          # Canonical config (Bloomberg, dashboard, multi-user settings)
└── dashboard/
    ├── app.py           # Dash web app + Flask-SocketIO (pricer, blotter, multi-user callbacks)
    └── layouts.py       # UI layout: username modal, pricer toolbar+table, order blotter
tests/
├── test_models.py       # 17 tests — payoffs, structures
├── test_parser.py       # 43 tests — extraction helpers + full order parsing for all IDB formats
├── test_order_store.py  # 12 tests — SQLite persistence (load, save, add, update, created_by)
├── test_pricer.py       # 23 tests — BS pricing, put-call parity, Greeks, structure pricing
└── test_structure_pricer.py # 11 tests — structure bid/offer/mid, sizes, ratio spreads
```

## Broker Shorthand Format
The parser handles flexible, messy real-world broker shorthand with tokens in any order:

**Stock reference:** `vs250.32`, `vs 250`, `vs. 250`, `tt69.86`, `tt 171.10`, `t 250`
**Delta:** `30d`, `3d`, `on a 11d`
**Quote side:** `20.50 bid`, `2.4b`, `@ 1.60`, `500 @ 2.55`, `5.00 offer`, `3.5o`
**Quantity:** `1058x`, `600x`, `2500x`, `1k` (= 1000), `2k` (= 2000)
**Strike+type:** `45P`, `300C`, `130p`, `240/220`
**Expiry:** `Jun26`, `Jan27`, `Apr` (no year = nearest upcoming)
**Structure types:** `PS` (put spread), `CS` (call spread), `Risky` (risk reversal), `straddle`, `strangle`, `fly` (butterfly), `collar`
**Ratios:** `1X2`, `1x3`
**Modifiers:** `putover`, `put over`, `callover`, `call over`, `1X over`

### Example Orders
```
AAPL jun26 300 calls vs250.32 30d 20.50 bid 1058x
UBER Jun26 45P tt69.86 3d 0.41 bid 1058x
QCOM 85P Jan27 tt141.17 7d 2.4b 600x
VST Apr 130p 500 @ 2.55 tt 171.10 on a 11d
IWM feb 257 apr 280 Risky vs 262.54 52d 2500x @ 1.60
AAPL Jun26 240/220 PS 1X2 vs250 15d 500x @ 3.50 1X over
```

## Dashboard Display
- **Username Modal:** Blocking overlay prompts for username on first load. Name stored in session-scoped `dcc.Store`. Displayed in header alongside connected user count.
- **Paste Order:** `dcc.Textarea` for broker shorthand input. Enter key triggers parse & price via clientside callback.
- **Pricer Toolbar:** Underlying | Structure | Tie | Delta | Order Price | Side | Qty | [Add Order] — dual-purpose: configures pricing AND submits to order blotter. Side/Qty/Price are all optional.
- **Header bar:** Title (left) + username + "(N online)" count (right). Plus: Ticker, structure type, tie price, current stock price, delta (+/-)
- **Pricing table:** Editable DataTable — Leg | Expiry | Strike | Type | Side | Qty | Bid Size | Bid | Mid | Offer | Offer Size. Editing triggers auto-reprice.
  - Structure row at bottom with implied bid/offer/mid and sizes
- **Broker quote section:** Shows broker price vs screen mid and edge
- **Order Blotter:** Shared across all users. 16 columns including "User" (created_by). 6 editable: side, size, traded, bought/sold, traded price, initiator. Column toggle via "Columns" button. Native sort (default: time desc). Click row to recall into pricer. PnL auto-calcs for traded orders. Data persists to `~/.options_pricer/orders.db` (SQLite).
- **Multi-user sync:** Flask-SocketIO broadcasts `blotter_changed` events when any user adds or edits an order. All clients receive updates via WebSocket. A 5-second `dcc.Interval` provides fallback polling if WebSocket disconnects.
- **Architecture:** Toolbar is always visible; "Add Order" validates a structure is priced. Hidden ID stubs (`order-input-section`, `order-side`, `order-size`) exist for Dash callback compatibility after the standalone order input section was removed.

## Key Concepts
- **Tied to (tt/vs):** The stock price at which the option package is quoted. Delta-hedged trades sell/buy stock at this price.
- **Delta-neutral packages:** Quantity × 100 × delta = stock hedge shares
- **Ratio spreads (1X2):** Unequal legs, e.g., sell 1x 240P, buy 2x 220P. "1X over" = 1 extra ratio on the buy side.
- **Putover/callover:** Which leg of a risk reversal is worth more (determines buy/sell direction)
- **Structure bid/offer:** Calculated from screen prices — bid uses worst fills (buy at offer, sell at bid), offer uses best fills

## Key Commands
```bash
source .venv/Scripts/activate          # Windows (Git Bash)
pytest tests/ -v                       # Run all 94 tests
python -m options_pricer.dashboard.app # Launch dashboard at http://127.0.0.1:8050
```

## UI Rules (MUST follow when editing layouts.py or any dashboard styling)
- **No content cutoff:** Never use `overflow: hidden` on containers that hold interactive content (toolbars, tables, inputs, dropdowns). Use `overflow: visible` or `overflow: auto` instead.
- **Box sizing:** All elements with `width: 100%` must also set `boxSizing: border-box` so padding/border don't cause overflow.
- **Max width:** The main layout container uses `maxWidth: 1400px`. Do not shrink this without good reason.
- **Text inputs that may contain long strings:** Use `dcc.Textarea` (not `dcc.Input`) so text wraps visibly. Set `minHeight: 80px`, `resize: vertical`, `lineHeight: 1.5`, and `boxSizing: border-box`. `dcc.Input` is single-line and clips long text — never use it for order/paste fields.
- **Enter key on Textarea:** `dcc.Textarea` does not support `n_submit`. Use a clientside callback that binds a `keydown` listener and calls `btn.click()` on Enter (see `app.py` for the pattern). Shift+Enter should still allow newlines.
- **Dropdowns in tables:** Dash DataTable dropdown columns can clip inside tight containers — ensure parent has `overflow: visible`.
- **Test visually:** After any layout change, confirm in the browser that all text, inputs, buttons, and table columns are fully visible and not clipped. Scroll horizontally if the table is wide (`overflowX: auto` on DataTable).
- **Consistent sizing:** Use monospace font at 13px for data cells, 16px for the order input. Keep padding consistent (8-14px for inputs, 10-14px for table cells).

## Current Status & Next Steps
- Parser handles all example formats provided so far (including `Nk` quantity format) — feed more real orders to refine
- Bloomberg API integrated but needs Terminal running for live data; mock works for dev
- Order Blotter with SQLite persistence, editable cells, column toggle, PnL auto-calc, and recall working
- Multi-user support: username prompt, shared blotter with "User" column, WebSocket live sync (up to 15 users)
- Settings module (`src/options_pricer/settings.py`) centralizes all config constants
- Next: delta adjustment for stock tie vs current price in structure pricing
- Next: more structure types as needed (iron condors, diagonals, etc.)
- Next: SPX/index options with combo pricing
- Note: structure_pricer.py bid/offer sign convention may need review (mid is correct, bid/offer labels may be swapped)

## GitHub
- Repo: https://github.com/hermanrockefeller-glitch/mycodebase.git
- Single branch: `main`
- Auth: HTTPS via `gh` credential helper
