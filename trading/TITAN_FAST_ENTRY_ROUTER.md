# TITAN Fast Entry Router — multi-strategy startup research

Objective: measure **new directional opportunities** immediately when the
existing six-agent scan starts, instead of requiring unanimity among
unrelated heuristics. The router adds three independent setup archetypes:

1. Donchian-style 20-bar breakout + quote-volume surge + EMA12/26 and
   completed 4-hour trend alignment + tape flow.
2. EMA20 pullback crossover in the direction of both higher timeframes.
3. Ten-candle liquidity sweep, reclaim/rejection, and confirmed tape flow.

It rejects stale or malformed candles, stale order books, low liquidity,
wide spreads, absent derivatives, inadequate tape sample, nonpositive
stop/target, high round-trip fee burden, and excessive stop distance.

Data used: already-fetched public OKX 15m, 1h, and 4h completed candles,
order book, trades and ticker. No additional API connections or secrets.

Output: per-market `fast_entry_research` inside the same
`reports/okx_six_agents.json` and
`fast_entry_research_candidates` counter.
Research emits potential LONG/SHORT/WAIT proposals and hypothetical stop/target.

**Important:** This router intentionally does NOT change the original
`signal` used by the real-money executor.
It does not place orders, open a live position at startup, validate a
profitable edge, or guarantee a trade or a 5-second scan.

Before authorizing a new strategy for real orders: collect forward-separated
public-market outcomes, cost/impact estimates and exchange-account stress,
then review its live execution and sizing risk. This preserves the owner's
explicit STOP state.

Run tests:
    python -m unittest discover -s tests -p test_titan_fast_entry_router.py -v
