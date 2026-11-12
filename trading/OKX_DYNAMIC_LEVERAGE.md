# TITAN Ω — variable leverage (10x–100x)

This feature is proposed on a **review branch**. It must not change running production settings until merged and explicitly configured.

## Modes
- `OKX_LEVERAGE_MODE=fixed` (default) retains 20x.
- `OKX_LEVERAGE_MODE=dynamic` selects an integer from 10x to 100x, or skips entry.
- For demo/live, also set repository secret `OKX_DYNAMIC_LEVERAGE_ARM=I_ACCEPT_VARIABLE_10_TO_100X_LIQUIDATION_RISK`. Existing execution arm, live enable and owner stop remain independent.
- `OKX_MAX_ACTIVE_POSITIONS=1..10` already supports multiple concurrent positions with `OKX_CAPITAL_MODE=adaptive_guarded` and separate `OKX_PORTFOLIO_ARM=YES`.

## How leverage is chosen
The executor obtains a current public instrument maximum and a fresh account-specific OKX `adjust-leverage-info` maximum. It extracts the Omega estimated round-trip cost and uses the actual proposed stop distance. A deterministic stress heuristic selects the largest candidate inside both caps and a 50% double-stop / 75% half-percent shock *margin* stress screen. If any required evidence is missing, stale, non-finite, or below 10x, entry is rejected. No expected-profit guarantee or liquidation price prediction is implied.

Existing positions are valued using their actual reported leverage to check portfolio margin; absent leverage metadata blocks dynamic multi-position entries. Aggregate initial-stop and margin caps and the separate 96%/full-margin single-position options remain in force.

## Important boundary
**Multi-position mode does not use the full account balance.** It uses `adaptive_guarded` and the existing 5% aggregate planned-stop risk / 50% portfolio initial-margin caps. The 100%-allocation multi-position scenario is available only in `trading/titan_portfolio_2037.py` research (zero live orders). A promise to keep 100% of equity in the market would require forced entries and could wipe out the entire balance rapidly at 100x. No order is submitted by this document or tests.

No credentials may be committed to GitHub source. Before any real-money use: pass tests, inspect OKX account mode/leverage tiers/portfolio protections, and activate separately.
