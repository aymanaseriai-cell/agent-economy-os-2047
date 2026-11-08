# QUANT2037 Adversarial Microstructure Twin

**Purpose:** falsify the original six-agent + seven-quant decision pipeline
using frozen REAL OKX public market data plus registered synthetic attacks.

This is NOT another indicator, not quantum computing, not a new trading
algorithm, and NOT evidence of profitability.

## Original decision rules

Uses the exact original research functions in trading/six_agent_council.py
and trading/quant2037.py: liquidity sentinel, volume-profile auction cartographer,
tape detective, funding and open-interest intelligence, higher-timeframe
structure, risk marshal, and all seven QUANT2037 systems.
The sole backwards-compatible adjustment is an optional asof_epoch for
liquidity book-age calculation, so a frozen snapshot replays deterministically
on another day; the default wall-clock behavior is unchanged.

## Attacker types

SIX mild attacks: displayed bid depth -20%; ask depth -20%;
flip side of latest 10% of public trades; widen bid/ask by 3bp;
raise or lower last quote by 5bp.

FIVE hostile attacks: fake 3x top-5 bid or ask wall; flip most recent 30%
trade sides; widen bid/ask 20bp; stale orderbook timestamp 150 seconds.

These are ARTIFICIAL counterfactual interventions for vulnerability testing.
They are NOT authenticated spoofing, wash trading, actual exchange outages
or market forecasts.

Each sample captures OHLCV (15m, 1h, 4h), 50 L2 book levels,
public trades, mark, OI and funding from PUBLIC endpoints only.
The raw inputs are frozen before attack and SHA256 hashed; all 11 variants
replay the exact six original specialist roles and seven quant systems.
We compare final decision, core direction, six role votes/vetoes, seven
system votes/risk codes. Exact original raw inputs and results are archived.
The SHA256 digest is change detection, not independent notarization.

## Real initial experiment on 2026-11-08

Source: reports/quant2037_adversary_raw_public.json.
Output: reports/quant2037_adversary_result.json.
Three real public market snapshots: BTC, ETH, ZEC swaps.
All three originally WAIT. None of 33 adversarial simulations changed
the final WAIT; hostile attacks changed FOUR core-role vote records
and SIX advanced-quant verdict records in total.
Mild attacks did not change the votes in these THREE observed snapshots.

IMPORTANT: Stable WAIT does NOT prove profitable alpha. No live-market
LONG or SHORT appeared in this first experiment, so fragility of REAL
candidates remains UNOBSERVED. A separate SYNTHETIC LONG fixture
verifies that hostile wide-spread or stale-book attacks can cause WAIT.

The 16 new unit tests cover original model behavior, immutable source
preservation, fixed-clock replay, book/tape stress, checksums and
absence of private endpoints.

## Reproduction (no API key)

    python -m unittest discover -s tests -p test_market_adversary.py -v
    python -m trading.market_adversary replay --evidence reports/quant2037_adversary_raw_public.json --out reports/replayed_adversary.json

Capture fresh public snapshots, without credentials:

    python -m trading.market_adversary capture --top 3 --evidence reports/new_public_inputs.json --out reports/new_stress.json

Scheduled GitHub workflow okx-market-adversary.yml uses public data
every six hours, can be manually run, and retains raw snapshots and results
for 30 days. GitHub schedule may be delayed.

## Limits and risks

- Book, trades and candles are fetched sequentially and NOT exchange-atomic.
- A single L2 snapshot cannot establish manipulative intent or spoofing.
- Mutations do not model adaptive market participants, fill queue
  priority, or executable price, and do not demonstrate profit or loss.
- NVIDIA advisory votes and future outcomes are NOT in these scenarios.
- No private OKX API endpoint, no leverage, no orders, no account access.
- The real-money workflow remains disabled by explicit user instruction.

Do not treat low flip rate or a green CI result as evidence of trading edge.
