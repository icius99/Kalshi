from __future__ import annotations

import math
from dataclasses import dataclass

from research.fees import STANDARD_TAKER_RATE, taker_fee
from research.temperature import probabilities_for_markets


@dataclass(frozen=True)
class Signal:
    market_ticker: str
    side: str
    entry_price: float
    available_qty: float
    quantity: int
    model_probability_yes: float
    fee_total: float
    estimated_edge: float


def evaluate_probabilities(
    markets: list[dict],
    probabilities: dict[str, float],
    min_edge: float = 0.05,
    execution_buffer: float = 0.01,
    min_qty: float = 10.0,
    max_contracts: int = 25,
    taker_rate: float = STANDARD_TAKER_RATE,
) -> list[Signal]:
    signals: list[Signal] = []

    for market in markets:
        ticker = market["market_ticker"]
        probability_yes = probabilities[ticker]
        ask = market.get("yes_ask")
        bid = market.get("yes_bid")
        yes_available = float(market.get("yes_ask_qty") or 0.0)
        no_available = float(market.get("yes_bid_qty") or 0.0)

        def consider(side: str, price: float, available: float, outcome_probability: float):
            if available < min_qty:
                return
            quantity = min(int(max_contracts), math.floor(available))
            if quantity < max(1, math.ceil(min_qty)):
                return

            fee = taker_fee(price, quantity, taker_rate)
            fee_per_contract = fee / quantity
            edge = outcome_probability - price - execution_buffer - fee_per_contract

            if edge >= min_edge:
                signals.append(
                    Signal(
                        ticker,
                        side,
                        price,
                        available,
                        quantity,
                        probability_yes,
                        fee,
                        edge,
                    )
                )

        if ask is not None:
            consider("YES", float(ask), yes_available, probability_yes)

        if bid is not None:
            no_ask = 1.0 - float(bid)
            consider("NO", no_ask, no_available, 1.0 - probability_yes)

    signals.sort(key=lambda item: item.estimated_edge, reverse=True)
    return signals


def evaluate_markets(
    markets: list[dict],
    model_mean_f: float,
    model_sigma_f: float,
    min_edge: float = 0.05,
    execution_buffer: float = 0.01,
    min_qty: float = 10.0,
    max_contracts: int = 25,
    taker_rate: float = STANDARD_TAKER_RATE,
) -> tuple[dict[str, float], list[Signal]]:
    """Legacy normal-model wrapper retained for tests/comparison work."""
    probabilities = probabilities_for_markets(markets, model_mean_f, model_sigma_f)
    signals = evaluate_probabilities(
        markets,
        probabilities,
        min_edge,
        execution_buffer,
        min_qty,
        max_contracts,
        taker_rate,
    )
    return probabilities, signals
