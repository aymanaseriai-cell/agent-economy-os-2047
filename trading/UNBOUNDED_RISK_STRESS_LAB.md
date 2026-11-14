# TITAN QUANT2037 — offline unbounded-risk stress laboratory

This is a **no-orders, no-credentials** simulation and is **not connected to the OKX live executor**.

Use it to study the consequences of removing hypothetical position-count,
notional exposure and leverage ceilings. **No risk limit is enforced on the
synthetic positions**, which can produce simulated losses greater than 100%
of initial equity and negative theoretical equity.

Run locally:

```bash
python -m trading.unbounded_risk_stress_lab
python -m unittest tests.test_unbounded_risk_stress_lab -v
python -m trading.unbounded_risk_stress_lab --equity 100 --positions-json '[{"symbol":"SYNTH","side":"long","notional":"10000","leverage":"100"}]' --shocks=-0.01,-0.05,0.05 --out reports/unbounded_risk_lab.json
```

The common-shock scenario assumes all instruments move by the same percentage;
real correlations, liquidity, forced liquidation, trading fees, funding, mark price
and slippage are NOT modeled. Its outputs must not be treated as valid live
orders, actual liquidation levels or expected profits.

**No changes** to `trading/okx_live_executor.py`, `trading/okx_portfolio_guard.py`,
`trading/okx_risk_watchdog.py`, GitHub live workflow, or real trading switches.
Existing `STOP_RISK` alarm remains active until the real account is corrected.
