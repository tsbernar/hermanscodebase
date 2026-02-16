"""Black-Scholes pricing engine and Greeks calculations."""

import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

from .models import OptionLeg, OptionStructure, OptionType


@dataclass
class OptionPrice:
    """Pricing result for a single option leg."""

    price: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


@dataclass
class StructurePrice:
    """Aggregated pricing result for a multi-leg structure."""

    total_price: float
    total_delta: float
    total_gamma: float
    total_theta: float
    total_vega: float
    total_rho: float
    leg_prices: list[OptionPrice]


def black_scholes_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: OptionType,
    q: float = 0.0,
) -> float:
    """Calculate Black-Scholes option price.

    Args:
        S: Current spot price of the underlying.
        K: Strike price.
        T: Time to expiration in years.
        r: Risk-free interest rate (annualized).
        sigma: Implied volatility (annualized).
        option_type: CALL or PUT.
        q: Continuous dividend yield.

    Returns:
        Option price.
    """
    if T <= 0:
        # At or past expiration: return intrinsic value
        if option_type == OptionType.CALL:
            return max(S - K, 0.0)
        return max(K - S, 0.0)

    d1, d2 = _d1_d2(S, K, T, r, sigma, q)

    if option_type == OptionType.CALL:
        price = S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    else:
        price = K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)

    return price


def greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: OptionType,
    q: float = 0.0,
) -> OptionPrice:
    """Calculate option price and all Greeks.

    Args:
        S: Current spot price.
        K: Strike price.
        T: Time to expiration in years.
        r: Risk-free rate (annualized).
        sigma: Implied volatility (annualized).
        option_type: CALL or PUT.
        q: Continuous dividend yield.

    Returns:
        OptionPrice with price and Greeks.
    """
    price = black_scholes_price(S, K, T, r, sigma, option_type, q)

    if T <= 0:
        # At expiry: delta is 0 or 1, other Greeks are 0
        in_the_money = (option_type == OptionType.CALL and S > K) or (
            option_type == OptionType.PUT and S < K
        )
        delta = (1.0 if option_type == OptionType.CALL else -1.0) if in_the_money else 0.0
        return OptionPrice(price=price, delta=delta, gamma=0.0, theta=0.0, vega=0.0, rho=0.0)

    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    exp_qt = math.exp(-q * T)
    exp_rt = math.exp(-r * T)

    # Gamma (same for calls and puts)
    gamma = exp_qt * norm.pdf(d1) / (S * sigma * math.sqrt(T))

    # Vega (same for calls and puts) — per 1% vol move
    vega = S * exp_qt * norm.pdf(d1) * math.sqrt(T) / 100.0

    if option_type == OptionType.CALL:
        delta = exp_qt * norm.cdf(d1)
        theta = (
            -S * exp_qt * norm.pdf(d1) * sigma / (2 * math.sqrt(T))
            + q * S * exp_qt * norm.cdf(d1)
            - r * K * exp_rt * norm.cdf(d2)
        ) / 365.0  # per calendar day
        rho = K * T * exp_rt * norm.cdf(d2) / 100.0  # per 1% rate move
    else:
        delta = exp_qt * (norm.cdf(d1) - 1)
        theta = (
            -S * exp_qt * norm.pdf(d1) * sigma / (2 * math.sqrt(T))
            - q * S * exp_qt * norm.cdf(-d1)
            + r * K * exp_rt * norm.cdf(-d2)
        ) / 365.0
        rho = -K * T * exp_rt * norm.cdf(-d2) / 100.0

    return OptionPrice(price=price, delta=delta, gamma=gamma, theta=theta, vega=vega, rho=rho)


def price_structure(
    structure: OptionStructure,
    spot: float,
    r: float,
    sigma: float | dict[float, float],
    T: float,
    q: float = 0.0,
) -> StructurePrice:
    """Price an entire option structure.

    Args:
        structure: The option structure to price.
        spot: Current spot price of the underlying.
        r: Risk-free rate.
        sigma: Implied vol — either a single float or a dict mapping strike -> vol.
        T: Time to expiration in years (overrides leg expiry for simplicity).
        q: Continuous dividend yield.

    Returns:
        StructurePrice with total and per-leg pricing.
    """
    leg_prices: list[OptionPrice] = []
    total_price = 0.0
    total_delta = 0.0
    total_gamma = 0.0
    total_theta = 0.0
    total_vega = 0.0
    total_rho = 0.0

    for leg in structure.legs:
        if isinstance(sigma, dict):
            vol = sigma.get(leg.strike)
            if vol is None:
                raise ValueError(
                    f"No vol provided for strike {leg.strike}. "
                    f"Available strikes: {sorted(sigma.keys())}"
                )
        else:
            vol = sigma
        result = greeks(spot, leg.strike, T, r, vol, leg.option_type, q)

        direction = leg.direction
        qty = leg.quantity
        scaled = OptionPrice(
            price=result.price * direction * qty,
            delta=result.delta * direction * qty,
            gamma=result.gamma * direction * qty,
            theta=result.theta * direction * qty,
            vega=result.vega * direction * qty,
            rho=result.rho * direction * qty,
        )
        leg_prices.append(scaled)

        total_price += scaled.price
        total_delta += scaled.delta
        total_gamma += scaled.gamma
        total_theta += scaled.theta
        total_vega += scaled.vega
        total_rho += scaled.rho

    return StructurePrice(
        total_price=total_price,
        total_delta=total_delta,
        total_gamma=total_gamma,
        total_theta=total_theta,
        total_vega=total_vega,
        total_rho=total_rho,
        leg_prices=leg_prices,
    )


def _d1_d2(
    S: float, K: float, T: float, r: float, sigma: float, q: float
) -> tuple[float, float]:
    """Calculate d1 and d2 for Black-Scholes formula."""
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2
