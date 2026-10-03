import requests

BASE = "https://external-api.kalshi.com/trade-api/v2"

# 1. Get the NYC daily-high-temperature series
series = requests.get(f"{BASE}/series/KXHIGHNY").json()

print("Series:")
print(series["series"]["title"])
print()

# 2. Get currently open markets in that series
markets = requests.get(
    f"{BASE}/markets",
    params={
        "series_ticker": "KXHIGHNY",
        "status": "open",
    },
).json()

print(f"Found {len(markets['markets'])} open markets\n")

for market in markets["markets"]:
    ticker = market["ticker"]

    book = requests.get(
        f"{BASE}/markets/{ticker}/orderbook"
    ).json()

    book_data = book["orderbook_fp"]

    yes_bids = book_data.get("yes_dollars") or []
    no_bids = book_data.get("no_dollars") or []

    best_yes_bid = max(yes_bids, key=lambda x: float(x[0])) if yes_bids else None
    best_no_bid = max(no_bids, key=lambda x: float(x[0])) if no_bids else None

    yes_bid = float(best_yes_bid[0]) if best_yes_bid else None
    yes_bid_qty = float(best_yes_bid[1]) if best_yes_bid else None

    no_bid = float(best_no_bid[0]) if best_no_bid else None
    no_bid_qty = float(best_no_bid[1]) if best_no_bid else None

    yes_ask = 1.0 - no_bid if no_bid is not None else None

    print()
    print(ticker)
    print(market["title"])
    print(f"  YES bid: {yes_bid:.2f} x {yes_bid_qty}" if yes_bid is not None else "  YES bid: None")
    print(f"  YES ask: {yes_ask:.2f} x {no_bid_qty}" if yes_ask is not None else "  YES ask: None")
    print(f"  Volume:  {market.get('volume_fp')}")

oct4 = [
    m for m in markets["markets"]
    if "26OCT04" in m["ticker"]
]

total_yes_bid = 0
total_yes_ask = 0

print("\nOCT 4 IMPLIED DISTRIBUTION")
print("-" * 60)

for market in oct4:
    ticker = market["ticker"]

    book = requests.get(
        f"{BASE}/markets/{ticker}/orderbook"
    ).json()["orderbook_fp"]

    yes_bids = book.get("yes_dollars") or []
    no_bids = book.get("no_dollars") or []

    best_yes_bid = (
        max(yes_bids, key=lambda x: float(x[0]))
        if yes_bids else None
    )

    best_no_bid = (
        max(no_bids, key=lambda x: float(x[0]))
        if no_bids else None
    )

    yes_bid = float(best_yes_bid[0]) if best_yes_bid else 0.0
    yes_ask = (
        1.0 - float(best_no_bid[0])
        if best_no_bid else 1.0
    )

    total_yes_bid += yes_bid
    total_yes_ask += yes_ask

    midpoint = (yes_bid + yes_ask) / 2

    print(
        f"{ticker:28} "
        f"bid={yes_bid:.2f} "
        f"ask={yes_ask:.2f} "
        f"mid={midpoint:.3f}"
    )

print("-" * 60)
print(f"Sum of YES bids: {total_yes_bid:.3f}")
print(f"Sum of YES asks: {total_yes_ask:.3f}")
print(f"Sum of mids:     {(total_yes_bid + total_yes_ask)/2:.3f}")

print()
print(
    f"Cost to buy all YES: ${total_yes_ask:.3f}"
)

n = len(oct4)

all_no_cost = n - total_yes_bid
all_no_payout = n - 1

print(
    f"Cost to buy all NO:  ${all_no_cost:.3f}"
)
print(
    f"Payout if exhaustive: ${all_no_payout:.2f}"
)
print(
    f"Gross all-NO edge:     "
    f"${all_no_payout - all_no_cost:.3f}"
)

event_ticker = oct4[0]["event_ticker"]

event = requests.get(
    f"{BASE}/events/{event_ticker}"
).json()["event"]

print("\nEVENT DETAILS")
print("-" * 60)

for key, value in event.items():
    print(f"{key}: {value}")

print("\nMARKET DEFINITIONS")
print("-" * 80)

for market in oct4:
    ticker = market["ticker"]

    detail = requests.get(
        f"{BASE}/markets/{ticker}"
    ).json()["market"]

    print(f"\n{ticker}")
    print(f"Title: {detail.get('title')}")
    
    for key in [
        "market_type",
        "floor_strike",
        "cap_strike",
        "functional_strike",
        "yes_sub_title",
        "no_sub_title",
        "rules_primary",
        "rules_secondary",
        "settlement_value",
        "close_time",
        "expiration_time",
    ]:
        if key in detail:
            print(f"{key}: {detail[key]}")