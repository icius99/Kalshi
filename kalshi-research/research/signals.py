from __future__ import annotations

from dataclasses import dataclass

from research.temperature import probabilities_for_markets


@dataclass(frozen=True)
class Signal:
    market_ticker: str
    side: str
    entry_price: float
    available_qty: float
    model_probability_yes: float
    estimated_edge: float


def evaluate_markets(
    markets: list[dict],
    model_mean_f: float,
    model_sigma_f: float,
    min_edge: float = 0.05,
    execution_buffer: float = 0.01,
    min_qty: float = 10.0,
) -> tuple[dict[str, float], list[Signal]]:
    probs = probabilities_for_markets(markets, model_mean_f, model_sigma_f)
    signals: list[Signal] = []

    for market in markets:
        ticker = market["market_ticker"]
        p = probs[ticker]
        ask = market.get("yes_ask")
        bid = market.get("yes_bid")
        yes_qty = float(market.get("yes_ask_qty") or 0.0)
        no_qty = float(market.get("yes_bid_qty") or 0.0)

        if ask is not None:
            yes_edge = p - float(ask) - execution_buffer
            if yes_edge >= min_edge and yes_qty >= min_qty:
                signals.append(
                    Signal(ticker, "YES", float(ask), yes_qty, p, yes_edge)
                )

        if bid is not None:
            no_ask = 1.0 - float(bid)
            no_edge = (1.0 - p) - no_ask - execution_buffer
            if no_edge >= min_edge and no_qty >= min_qty:
                signals.append(
                    Signal(ticker, "NO", no_ask, no_qty, p, no_edge)
                )

    signals.sort(key=lambda item: item.estimated_edge, reverse=True)
    return probs, signals
