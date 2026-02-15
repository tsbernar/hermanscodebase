# Options Pricer — Project Context

## What This Is
An options pricing tool for an IDB (inter-dealer broker) equity derivatives broker working US equity options (single stock, ETF, index). Parses broker shorthand orders, prices them with Black-Scholes, and displays results on a web dashboard.

## Tech Stack
- **Python 3.12** (venv at `.venv/`)
- **Dash (Plotly)** — web dashboard
- **NumPy / SciPy** — numerical pricing
- **blpapi** — Bloomberg Terminal API (optional; mock client used when unavailable)
- **pytest** — 57 tests, all passing

## Project Structure
```
src/options_pricer/
├── models.py        # OptionLeg, OptionStructure dataclasses + payoff math
├── parser.py        # Parses broker shorthand: "BUY 100 AAPL Jan25 150/160 call spread"
├── pricer.py        # Black-Scholes pricing engine + Greeks (delta, gamma, theta, vega, rho)
├── bloomberg.py     # BloombergClient + MockBloombergClient with 10 tickers of sample data
└── dashboard/
    ├── app.py       # Dash web app entry point + callbacks
    └── layouts.py   # UI layout components
tests/
├── test_models.py   # 17 tests — payoffs, structures
├── test_parser.py   # 16 tests — all structure types + error handling
└── test_pricer.py   # 24 tests — BS pricing, put-call parity, Greeks, structure pricing
config/
└── settings.py      # Bloomberg connection config, dashboard defaults
```

## Supported Option Structures
Single options, vertical spreads (call/put), straddles, strangles, butterflies, risk reversals, collars.

## Key Commands
```bash
source .venv/bin/activate
pytest tests/ -v              # Run all tests
python -m options_pricer.dashboard.app  # Launch dashboard at http://127.0.0.1:8050
```

## Design Decisions
- `MockBloombergClient` provides realistic sample data for 10 major tickers so everything works without a Bloomberg Terminal
- Parser uses simple token-based parsing of broker shorthand (not regex-heavy)
- Greeks are per calendar day (theta) and per 1% move (vega, rho)
- Vol skew in mock client: OTM puts get higher implied vol
- Pricing supports per-strike vol dict or flat vol

## GitHub
- Repo: https://github.com/hermanrockefeller-glitch/mycodebase.git
- Single branch: `main`
- Auth: HTTPS via `gh` credential helper
