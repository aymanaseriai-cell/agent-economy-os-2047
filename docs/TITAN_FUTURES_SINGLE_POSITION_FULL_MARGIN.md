# TITAN Futures — single-position full-margin configuration (high risk)

This branch change adjusts the account-wide isolated-margin hard limit to **100%**, without opening any orders. The repository must remain disarmed until the owner explicitly starts a run.

Expected GitHub Actions variables: `OKX_MAX_ACTIVE_POSITIONS=1`, `OKX_CAPITAL_MODE=full_margin`, `OKX_LEVERAGE_MODE=dynamic`. Live requires separate credential-based arming, explicit workflow confirmations, `OKX_ENABLE_REAL_TRADING=YES` and `OKX_STOP_CONTINUOUS=NO`.

**Actual execution:** For one position, the executor uses up to 100% of *available USDT equity* as isolated initial margin at the selected leverage, subject to contract granularity, fees, exchange max-size, current open positions, and mandatory per-trade planned-stop-loss veto (10% of free equity). It cannot guarantee full 100% allocation. Dynamic leverage is selected between 20x and 100x only if the shock/cost filters pass. No instrument is guaranteed to qualify.

**Not changed:** protective take-profit/stop-loss orders, post-submit protection verification, exchange max leverage/size checks, stop distance gates, and the 10% single-trade stop-risk veto. The 99% historical portfolio stop-risk monitoring gate remains a separate safety check; in the single-position execution path a new entry is sized by the 10% single-trade limit, not by the aggregate multiposition budget. Stop orders do **not** guarantee no liquidation or limit realized losses.

**Existing positions:** This mode refuses new trades if *any* SWAP position or conflicting pending order already exists. Stopping GitHub never closes or cancels an existing OKX position or TP/SL order. Never enable one-position full margin with old multi-position exposure unresolved.
