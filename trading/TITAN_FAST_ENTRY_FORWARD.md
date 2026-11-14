# TITAN Fast Entry prospective validation

This evaluates each separate research-only breakout, EMA pullback and sweep
proposal fixed at the time of each original 15-minute council scan.

- A hash-protected public snapshot stores direction, strategy, stop and target.
- A modified policy fingerprint now includes the fast router source.
- Outcome is the next complete candle OPEN after publication, then a fixed 1h
  horizon with conservative stop-first assumptions; absent protection/price
  history does not become a synthetic win.
- Fees, slippage and funding assumptions are stressed x2/x3/x2.
- Same-symbol episodes are deduplicated within 4 hours.
- Latest strategy version only; 70/30 chronological holdout with 4h embargo.
- A review threshold of >=100 matured episodes, >=14 UTC days, >=30 train
  and >=30 holdout is only an exploratory gate, NOT a backtest guarantee.
- No direct live execution, no private OKX APIs, no strategy promotion.

The new workflow may be executed manually or on a daily public-data research
schedule independent of the **disabled real-money trading workflow**.

Existing legacy snapshots without fast signals remain valid but contribute no
fast-entry episodes.
