"""Parse IDB broker shorthand for option structure orders.

Handles flexible token ordering and various broker conventions:
    "APPL jun26 300 calls vs250.32 30d 20.50 bid 1058x"
    "UBER Jun26 45P tt69.86 3d 0.41 bid 1058x"
    "QCOM 85P Jan27 tt141.17 7d 2.4b 600x"
    "VST Apr 130p 500 @ 2.55 tt 171.10 on a 11d"
    "IWM feb 257 apr 280 Risky vs 262.54 52d 2500x @ 1.60"
    "AAPL Jun26 240/220 PS 1X2 vs250 15d 500x @ 3.50 1X over"
"""

import re
from datetime import date

from .models import OptionLeg, OptionStructure, OptionType, Side, QuoteSide, ParsedOrder

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_MONTH_PATTERN = "|".join(_MONTHS.keys())

_STRUCTURE_ALIASES = {
    "ps": "put_spread",
    "cs": "call_spread",
    "put spread": "put_spread",
    "call spread": "call_spread",
    "risky": "risk_reversal",
    "risk reversal": "risk_reversal",
    "rr": "risk_reversal",
    "strad": "straddle",
    "straddle": "straddle",
    "strangle": "strangle",
    "fly": "butterfly",
    "butterfly": "butterfly",
    "collar": "collar",
}


def parse_order(text: str) -> ParsedOrder:
    """Parse an IDB broker shorthand order string into a ParsedOrder.

    Args:
        text: Order string in IDB broker shorthand.

    Returns:
        ParsedOrder with parsed structure and metadata.

    Raises:
        ValueError: If the order string cannot be parsed.
    """
    original = text.strip()
    if not original:
        raise ValueError("Empty order string")

    stock_ref = _extract_stock_ref(original)
    delta = _extract_delta(original)
    quantity = _extract_quantity(original)
    price, quote_side = _extract_price_and_side(original)
    ratio_tuple = _extract_ratio(original)
    modifier = _extract_modifier(original)
    structure_type = _extract_structure_type(original)
    is_live = _extract_is_live(original)
    delta_direction = _extract_delta_direction(original)

    # Parse core: ticker, expiries, strikes, option type
    ticker, leg_specs, default_opt_type = _parse_core(original, structure_type)

    if not ticker:
        raise ValueError(f"Cannot identify ticker in: {original}")

    # Infer structure type from context if not explicit
    if not structure_type:
        if len(leg_specs) == 1:
            structure_type = "single"
        elif len(leg_specs) == 2:
            # Two expiry/strike pairs with no structure keyword
            s1_type = leg_specs[0].get("type")
            s2_type = leg_specs[1].get("type")
            if s1_type and s2_type and s1_type != s2_type:
                structure_type = "risk_reversal"
            elif default_opt_type:
                structure_type = (
                    "put_spread" if default_opt_type == OptionType.PUT else "call_spread"
                )
            else:
                structure_type = "spread"

    # Build legs
    legs = _build_legs(
        ticker, leg_specs, default_opt_type, structure_type,
        ratio_tuple, modifier, quantity or 1,
    )

    # Build structure
    display_name = (structure_type or "single").replace("_", " ")
    structure = OptionStructure(
        name=display_name,
        legs=legs,
        description=original,
    )

    # LIVE = options only, no stock hedge
    if is_live:
        stock_ref = 0.0
        delta = 0.0

    # Apply delta sign from direction qualifier
    if delta and delta_direction:
        if delta_direction == "put":
            delta = -abs(delta)
        elif delta_direction == "call":
            delta = abs(delta)
        elif delta_direction == "1x":
            # "delta to the 1x": for CS the 1x is the buy leg (positive delta),
            # for PS the 1x is the sell leg (also positive delta — short put)
            if structure_type in ("call_spread", "put_spread"):
                delta = abs(delta)
        elif delta_direction == "2x":
            # "delta to the 2x": opposite direction
            if structure_type == "call_spread":
                delta = -abs(delta)
            elif structure_type == "put_spread":
                delta = -abs(delta)

    return ParsedOrder(
        underlying=ticker.upper(),
        structure=structure,
        stock_ref=stock_ref or 0.0,
        delta=delta or 0.0,
        price=price or 0.0,
        quote_side=quote_side or QuoteSide.BID,
        quantity=quantity or 0,
        raw_text=original,
    )


# ---------------------------------------------------------------------------
# Extraction helpers (regex-based, order-independent)
# ---------------------------------------------------------------------------

def _extract_stock_ref(text: str) -> float | None:
    """Extract stock reference price: vs250.32, tt69.86, t 171.10, vs. 250."""
    patterns = [
        r'\bvs\.?\s*(\d+\.?\d*)',
        r'\btt\s*(\d+\.?\d*)',
        r'\bt\s+(\d+\.?\d*)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None


def _extract_delta(text: str) -> float | None:
    """Extract delta: 30d, 3d, on a 11d, +20d, -15d."""
    m = re.search(r'(?:on\s+a\s+)?([+-]?\d+)\s*d\b', text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


def _extract_quantity(text: str) -> int | None:
    """Extract contract quantity: 1058x, 600x, 2500x."""
    m = re.search(r'(\d+)\s*x\b', text, re.IGNORECASE)
    if m:
        # Avoid matching ratio patterns like 1X2
        val = int(m.group(1))
        # Check it's not part of a ratio (1X2) by looking at what follows 'x'
        end = m.end()
        if end < len(text) and text[end:end+1].isdigit():
            # This is a ratio like 1X2, not a quantity
            # Look for another quantity pattern later
            rest = text[end:]
            m2 = re.search(r'(\d+)\s*x\b', rest, re.IGNORECASE)
            if m2 and not (m2.end() < len(rest) and rest[m2.end():m2.end()+1].isdigit()):
                return int(m2.group(1))
            return None
        return val
    return None


def _extract_price_and_side(text: str) -> tuple[float | None, QuoteSide | None]:
    """Extract price and quote side from various formats.

    Formats: "20.50 bid", "2.4b", "@ 1.60", "500 @ 2.55", "0.41 offer"
    """
    # Price with bid/offer word
    m = re.search(r'(\d+\.?\d*)\s+(?:bid)\b', text, re.IGNORECASE)
    if m:
        return float(m.group(1)), QuoteSide.BID

    m = re.search(r'(\d+\.?\d*)\s+(?:offer|ask)\b', text, re.IGNORECASE)
    if m:
        return float(m.group(1)), QuoteSide.OFFER

    # Price with b/o suffix: "2.4b", "3.5o"
    m = re.search(r'(\d+\.?\d*)b\b', text, re.IGNORECASE)
    if m:
        # Make sure it's not part of a word
        return float(m.group(1)), QuoteSide.BID

    m = re.search(r'(\d+\.?\d*)o\b', text, re.IGNORECASE)
    if m:
        return float(m.group(1)), QuoteSide.OFFER

    # @ price (offer convention)
    m = re.search(r'@\s*(\d+\.?\d*)', text, re.IGNORECASE)
    if m:
        return float(m.group(1)), QuoteSide.OFFER

    # "at X.XX" convention
    m = re.search(r'\bat\s+(\d+\.?\d*)\b', text, re.IGNORECASE)
    if m:
        return float(m.group(1)), QuoteSide.OFFER

    return None, None


def _extract_ratio(text: str) -> tuple[int, int] | None:
    """Extract ratio: 1X2, 1x2, 1x3."""
    m = re.search(r'\b(\d+)\s*[Xx]\s*(\d+)\b', text)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        # Distinguish ratio (1X2) from quantity (500x)
        if b > 1 and a < b:
            return (a, b)
    return None


def _extract_modifier(text: str) -> str | None:
    """Extract modifier: putover, callover, Nx over, put over, call over."""
    m = re.search(r'\b(\d+)[Xx]\s+over\b', text, re.IGNORECASE)
    if m:
        return f"{m.group(1)}x_over"

    m = re.search(r'\bput\s*over\b', text, re.IGNORECASE)
    if m:
        return "putover"

    m = re.search(r'\bcall\s*over\b', text, re.IGNORECASE)
    if m:
        return "callover"

    return None


def _extract_is_live(text: str) -> bool:
    """Check if the order is LIVE (no stock hedge, options only)."""
    return bool(re.search(r'\bLIVE\b', text, re.IGNORECASE))


def _extract_delta_direction(text: str) -> str | None:
    """Extract delta direction qualifier.

    Returns:
        "call" for positive/call-like delta,
        "put" for negative/put-like delta,
        "1x" for delta to the 1x leg,
        "2x" for delta to the 2x leg,
        None if no direction specified.
    """
    # "delta to the 1x" / "delta to the 2x"
    m = re.search(r'\bdelta\s+to\s+the\s+(\d+)x\b', text, re.IGNORECASE)
    if m:
        return f"{m.group(1)}x"

    # "delta to put" / "delta to call" / "delta like put" / "delta like call"
    m = re.search(
        r'\bdelta\s+(?:to|like)\s+(put|call)\b', text, re.IGNORECASE
    )
    if m:
        return m.group(1).lower()

    return None


def _extract_structure_type(text: str) -> str | None:
    """Extract structure type from text."""
    text_lower = text.lower()

    # Check multi-word patterns first
    for alias, canonical in sorted(_STRUCTURE_ALIASES.items(), key=lambda x: -len(x[0])):
        pattern = r'\b' + re.escape(alias) + r'\b'
        if re.search(pattern, text_lower):
            return canonical

    return None


# ---------------------------------------------------------------------------
# Core parsing: ticker, expiries, strikes, option type
# ---------------------------------------------------------------------------

def parse_expiry(expiry_str: str, year_str: str | None = None) -> date:
    """Parse expiry like 'Jun26' -> date(2026, 6, 16)."""
    month_str = expiry_str[:3].lower()
    month = _MONTHS.get(month_str)
    if month is None:
        raise ValueError(f"Unknown month: {expiry_str}")

    if year_str:
        year = 2000 + int(year_str)
    else:
        # No year: use nearest upcoming occurrence
        today = date.today()
        year = today.year
        if month <= today.month:
            year += 1

    # Approximate standard expiry as 3rd Friday (day ~16)
    return date(year, month, 16)


def _parse_core(text: str, structure_type: str | None) -> tuple[
    str, list[dict], OptionType | None
]:
    """Parse the core components: ticker, expiry/strike pairs, option type.

    Returns:
        (ticker, leg_specs, default_option_type)
        where leg_specs is a list of dicts with keys: expiry, strike, type (optional)
    """
    # Tokenize
    tokens = text.strip().split()

    # Ticker is always the first token (alphabetical)
    ticker = tokens[0] if tokens else ""

    # Collect expiry/strike pairs and option type
    leg_specs: list[dict] = []
    default_opt_type: OptionType | None = None

    # Build a clean list of tokens to scan (skip metadata we've already extracted)
    # We need to find: month tokens, strike tokens, option type tokens
    i = 1  # skip ticker
    current_expiry = None

    # Patterns to skip during core parsing
    skip_patterns = [
        r'^(?:vs\.?|tt?)$',  # stock ref prefix
        r'^\d+\.?\d*$',  # bare numbers (could be stock ref value, price, etc.)
        r'^\d+x$',  # quantity
        r'^(?:bid|offer|ask|at)$',
        r'^(?:on|a)$',
        r'^[+-]?\d+d$',  # delta (including +20d, -15d)
        r'^(?:delta|live)$',  # delta direction / live qualifier
        r'^(?:the|like|to)$',  # parts of "delta to the 1x" etc.
        r'^@',
        r'^(?:' + '|'.join(re.escape(a) for a in _STRUCTURE_ALIASES.keys()
                           if ' ' not in a) + r')$',
        r'^\d+x\d+$',  # ratio
        r'^(?:put|call)\s*over$',
        r'^\d+x$',
        r'^over$',
    ]

    while i < len(tokens):
        token = tokens[i]
        token_lower = token.lower().rstrip('.,;')

        # Check for month (expiry start)
        month_match = re.match(r'^(' + _MONTH_PATTERN + r')(\d{2})?$', token_lower)
        if month_match:
            month_str = month_match.group(1)
            year_str = month_match.group(2)

            # Year must be part of the month token (e.g. "jun26"), never a
            # separate token.  A standalone number after the month is a strike.
            current_expiry = parse_expiry(month_str, year_str)

            # Look ahead for strike
            if i + 1 < len(tokens):
                next_tok = tokens[i + 1]
                strike_match = re.match(r'^(\d+\.?\d*)([PCpc])?$', next_tok)
                if strike_match:
                    strike_val = float(strike_match.group(1))
                    type_char = strike_match.group(2)
                    opt_type = None
                    if type_char:
                        opt_type = (
                            OptionType.CALL if type_char.upper() == 'C'
                            else OptionType.PUT
                        )
                    leg_specs.append({
                        "expiry": current_expiry,
                        "strike": strike_val,
                        "type": opt_type,
                    })
                    i += 2

                    # Check for additional space-separated strikes (e.g. "250 240 PS")
                    _MULTI_LEG = {
                        "put_spread", "call_spread", "spread",
                        "risk_reversal", "strangle", "butterfly",
                    }
                    while i < len(tokens):
                        next_strike = re.match(
                            r'^(\d+\.?\d*)([PCpc])?$', tokens[i]
                        )
                        if not next_strike:
                            break
                        ns_val = float(next_strike.group(1))
                        ns_type_char = next_strike.group(2)
                        # Only grab as a strike if structure needs multiple legs
                        # or the token right after is a structure keyword
                        is_multi = structure_type in _MULTI_LEG
                        next_is_struct = (
                            i + 1 < len(tokens)
                            and tokens[i + 1].lower() in _STRUCTURE_ALIASES
                        )
                        if not is_multi and not next_is_struct:
                            break
                        ns_opt = None
                        if ns_type_char:
                            ns_opt = (
                                OptionType.CALL if ns_type_char.upper() == 'C'
                                else OptionType.PUT
                            )
                        leg_specs.append({
                            "expiry": current_expiry,
                            "strike": ns_val,
                            "type": ns_opt,
                        })
                        i += 1

                    continue

                # Check for slash strikes: "240/220"
                slash_match = re.match(
                    r'^(\d+\.?\d*)(?:[PCpc])?/(\d+\.?\d*)(?:[PCpc])?$', next_tok
                )
                if slash_match:
                    s1 = float(slash_match.group(1))
                    s2 = float(slash_match.group(2))
                    # Check for type chars in slash notation
                    full_match = re.match(
                        r'^(\d+\.?\d*)([PCpc])?/(\d+\.?\d*)([PCpc])?$', next_tok
                    )
                    t1 = t2 = None
                    if full_match.group(2):
                        t1 = (
                            OptionType.CALL if full_match.group(2).upper() == 'C'
                            else OptionType.PUT
                        )
                    if full_match.group(4):
                        t2 = (
                            OptionType.CALL if full_match.group(4).upper() == 'C'
                            else OptionType.PUT
                        )
                    leg_specs.append({
                        "expiry": current_expiry, "strike": s1, "type": t1,
                    })
                    leg_specs.append({
                        "expiry": current_expiry, "strike": s2, "type": t2,
                    })
                    i += 2
                    continue

            i += 1
            continue

        # Check for strike with type suffix (no preceding month): "45P", "85P"
        strike_type_match = re.match(r'^(\d+\.?\d*)([PCpc])$', token)
        if strike_type_match:
            strike_val = float(strike_type_match.group(1))
            type_char = strike_type_match.group(2)
            opt_type = (
                OptionType.CALL if type_char.upper() == 'C'
                else OptionType.PUT
            )
            # Look ahead for month after strike (e.g. "85P Jan27")
            if i + 1 < len(tokens):
                next_lower = tokens[i + 1].lower()
                ahead_month = re.match(
                    r'^(' + _MONTH_PATTERN + r')(\d{2})?$', next_lower
                )
                if ahead_month:
                    expiry = parse_expiry(
                        ahead_month.group(1), ahead_month.group(2)
                    )
                    leg_specs.append({
                        "expiry": expiry, "strike": strike_val, "type": opt_type,
                    })
                    i += 2
                    continue

            # Use current expiry if we have one
            leg_specs.append({
                "expiry": current_expiry,
                "strike": strike_val,
                "type": opt_type,
            })
            i += 1
            continue

        # Check for slash strikes without preceding month: "240/220"
        slash_match = re.match(
            r'^(\d+\.?\d*)([PCpc])?/(\d+\.?\d*)([PCpc])?$', token
        )
        if slash_match:
            s1 = float(slash_match.group(1))
            s2 = float(slash_match.group(3))
            t1 = t2 = None
            if slash_match.group(2):
                t1 = (
                    OptionType.CALL if slash_match.group(2).upper() == 'C'
                    else OptionType.PUT
                )
            if slash_match.group(4):
                t2 = (
                    OptionType.CALL if slash_match.group(4).upper() == 'C'
                    else OptionType.PUT
                )
            leg_specs.append({
                "expiry": current_expiry, "strike": s1, "type": t1,
            })
            leg_specs.append({
                "expiry": current_expiry, "strike": s2, "type": t2,
            })
            i += 1
            continue

        # Check for option type word: "calls", "puts", "call", "put"
        # Skip if part of "delta to/like call/put" or "call/put over"
        prev_lower = tokens[i - 1].lower() if i > 0 else ""
        next_lower = tokens[i + 1].lower() if i + 1 < len(tokens) else ""
        is_delta_phrase = prev_lower in ("to", "like")
        is_over_phrase = next_lower == "over"
        if token_lower in ("call", "calls") and not is_delta_phrase and not is_over_phrase:
            default_opt_type = OptionType.CALL
            i += 1
            continue
        if token_lower in ("put", "puts") and not is_delta_phrase and not is_over_phrase:
            default_opt_type = OptionType.PUT
            i += 1
            continue

        # Check for bare strike number followed by "calls" or "puts"
        # Skip if the call/put is part of "call over" / "put over" / "delta to call"
        bare_strike = re.match(r'^(\d+\.?\d*)$', token)
        if bare_strike and i + 1 < len(tokens):
            next_lower = tokens[i + 1].lower()
            if next_lower in ("call", "calls", "put", "puts"):
                after_next = tokens[i + 2].lower() if i + 2 < len(tokens) else ""
                if after_next != "over":
                    strike_val = float(bare_strike.group(1))
                    opt_type = (
                        OptionType.CALL if next_lower.startswith("call")
                        else OptionType.PUT
                    )
                    default_opt_type = opt_type
                    leg_specs.append({
                        "expiry": current_expiry,
                        "strike": strike_val,
                        "type": opt_type,
                    })
                    i += 2
                    continue

        i += 1

    return ticker.upper(), leg_specs, default_opt_type


# ---------------------------------------------------------------------------
# Leg building
# ---------------------------------------------------------------------------

def _build_legs(
    ticker: str,
    leg_specs: list[dict],
    default_opt_type: OptionType | None,
    structure_type: str | None,
    ratio_tuple: tuple[int, int] | None,
    modifier: str | None,
    quantity: int,
) -> list[OptionLeg]:
    """Build option legs from parsed components."""

    if not leg_specs:
        raise ValueError("No strikes/expiries found in order")

    # Resolve option types
    for spec in leg_specs:
        if spec.get("type") is None:
            spec["type"] = default_opt_type

    # Determine ratios
    r1, r2 = (1, 1) if ratio_tuple is None else ratio_tuple

    st = structure_type or "single"

    if st == "single":
        return _build_single(ticker, leg_specs, quantity)
    elif st in ("put_spread", "call_spread", "spread"):
        return _build_spread(ticker, leg_specs, st, quantity, r1, r2)
    elif st == "risk_reversal":
        return _build_risk_reversal(ticker, leg_specs, quantity, modifier)
    elif st == "straddle":
        return _build_straddle(ticker, leg_specs, quantity)
    elif st == "strangle":
        return _build_strangle(ticker, leg_specs, quantity)
    elif st == "butterfly":
        return _build_butterfly(ticker, leg_specs, quantity, default_opt_type)
    elif st == "collar":
        return _build_collar(ticker, leg_specs, quantity)
    else:
        raise ValueError(f"Unknown structure type: {st}")


def _resolve_type(spec: dict, fallback: OptionType | None = None) -> OptionType:
    """Resolve option type from spec or fallback."""
    t = spec.get("type") or fallback
    if t is None:
        raise ValueError(
            f"Cannot determine option type for strike {spec.get('strike')}"
        )
    return t


def _build_single(ticker: str, specs: list[dict], quantity: int) -> list[OptionLeg]:
    spec = specs[0]
    return [OptionLeg(
        underlying=ticker, expiry=spec["expiry"], strike=spec["strike"],
        option_type=_resolve_type(spec), side=Side.BUY, quantity=quantity,
    )]


def _build_spread(
    ticker: str, specs: list[dict], spread_type: str,
    quantity: int, r1: int, r2: int,
) -> list[OptionLeg]:
    if len(specs) < 2:
        raise ValueError("Spread requires at least 2 strikes")

    s1, s2 = specs[0], specs[1]

    # Determine option type for spread
    if spread_type == "put_spread":
        opt_type = OptionType.PUT
    elif spread_type == "call_spread":
        opt_type = OptionType.CALL
    else:
        opt_type = _resolve_type(s1, s2.get("type"))

    # For put spread 1xN: sell higher strike (1x), buy lower strike (Nx)
    # For call spread 1xN: buy lower strike (1x), sell higher strike (Nx)
    high_strike = max(s1["strike"], s2["strike"])
    low_strike = min(s1["strike"], s2["strike"])
    high_spec = s1 if s1["strike"] >= s2["strike"] else s2
    low_spec = s2 if s1["strike"] >= s2["strike"] else s1

    if opt_type == OptionType.PUT:
        # Put spread: sell higher (r1), buy lower (r2)
        return [
            OptionLeg(
                underlying=ticker, expiry=high_spec["expiry"],
                strike=high_strike, option_type=OptionType.PUT,
                side=Side.SELL, quantity=quantity * r1,
            ),
            OptionLeg(
                underlying=ticker, expiry=low_spec["expiry"],
                strike=low_strike, option_type=OptionType.PUT,
                side=Side.BUY, quantity=quantity * r2,
            ),
        ]
    else:
        # Call spread: buy lower (r1), sell higher (r2)
        return [
            OptionLeg(
                underlying=ticker, expiry=low_spec["expiry"],
                strike=low_strike, option_type=OptionType.CALL,
                side=Side.BUY, quantity=quantity * r1,
            ),
            OptionLeg(
                underlying=ticker, expiry=high_spec["expiry"],
                strike=high_strike, option_type=OptionType.CALL,
                side=Side.SELL, quantity=quantity * r2,
            ),
        ]


def _build_risk_reversal(
    ticker: str, specs: list[dict], quantity: int, modifier: str | None,
) -> list[OptionLeg]:
    if len(specs) < 2:
        raise ValueError("Risk reversal requires 2 strikes")

    s1, s2 = specs[0], specs[1]

    # Determine which is put, which is call
    # If types are explicit, use them
    if s1.get("type") and s2.get("type"):
        put_spec = s1 if s1["type"] == OptionType.PUT else s2
        call_spec = s2 if s1["type"] == OptionType.PUT else s1
    else:
        # Convention: lower strike is put, higher strike is call
        if s1["strike"] <= s2["strike"]:
            put_spec, call_spec = s1, s2
        else:
            put_spec, call_spec = s2, s1

    # Default: sell put, buy call (bullish risk reversal)
    # Modifier can flip this
    if modifier == "putover":
        # Buyer buys put, sells call
        return [
            OptionLeg(
                underlying=ticker, expiry=put_spec["expiry"],
                strike=put_spec["strike"], option_type=OptionType.PUT,
                side=Side.BUY, quantity=quantity,
            ),
            OptionLeg(
                underlying=ticker, expiry=call_spec["expiry"],
                strike=call_spec["strike"], option_type=OptionType.CALL,
                side=Side.SELL, quantity=quantity,
            ),
        ]
    else:
        # Default or callover: sell put, buy call
        return [
            OptionLeg(
                underlying=ticker, expiry=put_spec["expiry"],
                strike=put_spec["strike"], option_type=OptionType.PUT,
                side=Side.SELL, quantity=quantity,
            ),
            OptionLeg(
                underlying=ticker, expiry=call_spec["expiry"],
                strike=call_spec["strike"], option_type=OptionType.CALL,
                side=Side.BUY, quantity=quantity,
            ),
        ]


def _build_straddle(
    ticker: str, specs: list[dict], quantity: int,
) -> list[OptionLeg]:
    if len(specs) < 1:
        raise ValueError("Straddle requires at least 1 strike")
    spec = specs[0]
    return [
        OptionLeg(
            underlying=ticker, expiry=spec["expiry"], strike=spec["strike"],
            option_type=OptionType.CALL, side=Side.BUY, quantity=quantity,
        ),
        OptionLeg(
            underlying=ticker, expiry=spec["expiry"], strike=spec["strike"],
            option_type=OptionType.PUT, side=Side.BUY, quantity=quantity,
        ),
    ]


def _build_strangle(
    ticker: str, specs: list[dict], quantity: int,
) -> list[OptionLeg]:
    if len(specs) < 2:
        raise ValueError("Strangle requires 2 strikes")
    sorted_specs = sorted(specs, key=lambda s: s["strike"])
    return [
        OptionLeg(
            underlying=ticker, expiry=sorted_specs[0]["expiry"],
            strike=sorted_specs[0]["strike"], option_type=OptionType.PUT,
            side=Side.BUY, quantity=quantity,
        ),
        OptionLeg(
            underlying=ticker, expiry=sorted_specs[1]["expiry"],
            strike=sorted_specs[1]["strike"], option_type=OptionType.CALL,
            side=Side.BUY, quantity=quantity,
        ),
    ]


def _build_butterfly(
    ticker: str, specs: list[dict], quantity: int,
    default_opt_type: OptionType | None,
) -> list[OptionLeg]:
    if len(specs) < 3:
        raise ValueError("Butterfly requires 3 strikes")
    sorted_specs = sorted(specs, key=lambda s: s["strike"])
    opt_type = sorted_specs[0].get("type") or default_opt_type or OptionType.CALL
    return [
        OptionLeg(
            underlying=ticker, expiry=sorted_specs[0]["expiry"],
            strike=sorted_specs[0]["strike"], option_type=opt_type,
            side=Side.BUY, quantity=quantity,
        ),
        OptionLeg(
            underlying=ticker, expiry=sorted_specs[1]["expiry"],
            strike=sorted_specs[1]["strike"], option_type=opt_type,
            side=Side.SELL, quantity=quantity * 2,
        ),
        OptionLeg(
            underlying=ticker, expiry=sorted_specs[2]["expiry"],
            strike=sorted_specs[2]["strike"], option_type=opt_type,
            side=Side.BUY, quantity=quantity,
        ),
    ]


def _build_collar(
    ticker: str, specs: list[dict], quantity: int,
) -> list[OptionLeg]:
    if len(specs) < 2:
        raise ValueError("Collar requires 2 strikes")
    sorted_specs = sorted(specs, key=lambda s: s["strike"])
    return [
        OptionLeg(
            underlying=ticker, expiry=sorted_specs[0]["expiry"],
            strike=sorted_specs[0]["strike"], option_type=OptionType.PUT,
            side=Side.BUY, quantity=quantity,
        ),
        OptionLeg(
            underlying=ticker, expiry=sorted_specs[1]["expiry"],
            strike=sorted_specs[1]["strike"], option_type=OptionType.CALL,
            side=Side.SELL, quantity=quantity,
        ),
    ]
