from __future__ import annotations

import math

STANDARD_TAKER_RATE = 0.07
FEE_SCHEDULE_EFFECTIVE = "2026-07-07"


def taker_fee(price: float, contracts: int, rate: float = STANDARD_TAKER_RATE) -> float:
    """Standard Kalshi event-contract taker fee, rounded up to the next cent.

    This applies to standard event-contract markets; series-specific fee
    multipliers must be handled separately when we expand beyond KXHIGHNY.
    """
    if not 0.0 <= price <= 1.0:
        raise ValueError("price must be between 0 and 1")
    if contracts < 0 or int(contracts) != contracts:
        raise ValueError("contracts must be a non-negative integer")
    raw = rate * int(contracts) * price * (1.0 - price)
    return math.ceil((raw - 1e-12) * 100.0) / 100.0
