# TITAN Ω — stronger variable leverage (20x–100x)

## Configuration
- `OKX_LEVERAGE_MODE=fixed` remains the 20x fallback; `dynamic` uses **20x–100x** or rejects a candidate.
- Dynamic mode requires current OKX instrument and account-specific leverage tier ceilings. If either is below 20x, or the required stress checks fail even at 20x, **no order** is allowed.
- Keep the already configured repository secret `OKX_DYNAMIC_LEVERAGE_ARM=I_ACCEPT_VARIABLE_10_TO_100X_LIQUIDATION_RISK`. Its historical name remains unchanged for compatibility; the selector itself uses **20x–100x**.
- Separate live `OKX_EXECUTION_ARM` secret, owner stop switches, explicit workflow confirmations, and exchange order protection remain necessary.

## Risk and protection
The algorithm chooses the largest allowed leverage between 20x and 100x that survives a double-stop/fee stress screen and 0.5% adverse-price shock heuristic. These screens are not a liquidation guarantee. Fixed entry criteria remain symmetrical for LONG and SHORT (at least a two-point lead with at least two voting agents), plus seven quant and Omega checks.

For portfolio exposure, at most **25 separately TP/SL-protected isolated USDT swap positions** are allowed, with **99% of equity** as the aggregate planned-stop and isolated-margin ceilings. Both are ceilings, **not targets, realized-loss limits, or a guarantee of available buying power**. In default `adaptive_guarded` mode, each candidate is still sized against **2% of free equity at its initial stop** and **20% of free equity in isolated margin**. Liquidation, gaps, slippage, and fees can cause losses beyond modeled stop-risk.

The live bot does not restart by merely merging code. The owner must explicitly enable and launch the GitHub Actions LIVE workflow after tests and a read-only OKX check. Repository source files never store API keys.
