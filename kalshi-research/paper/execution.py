from __future__ import annotations

from datetime import datetime, timezone

from collector import get_best_prices, get_orderbook
from research.signals import evaluate_probabilities


def fetch_live_execution_markets(markets: list[dict]) -> tuple[str, list[dict]]:
    """Refresh executable quotes from Kalshi public orderbooks."""
    timestamp = datetime.now(timezone.utc).isoformat()
    refreshed = []

    for market in markets:
        book = get_orderbook(market["market_ticker"])
        yes_bid, yes_bid_qty, yes_ask, yes_ask_qty = get_best_prices(book)
        updated = dict(market)
        updated.update(
            {
                "yes_bid": yes_bid,
                "yes_bid_qty": yes_bid_qty,
                "yes_ask": yes_ask,
                "yes_ask_qty": yes_ask_qty,
            }
        )
        refreshed.append(updated)

    return timestamp, refreshed


def revalidate_signals(
    markets: list[dict],
    probabilities: dict[str, float],
    min_edge: float,
    execution_buffer: float,
    min_qty: float,
    max_contracts: int,
) -> tuple[str, list[dict], list]:
    execution_quote_utc, refreshed = fetch_live_execution_markets(markets)
    signals = evaluate_probabilities(
        refreshed,
        probabilities,
        min_edge,
        execution_buffer,
        min_qty,
        max_contracts,
    )
    return execution_quote_utc, refreshed, signals
