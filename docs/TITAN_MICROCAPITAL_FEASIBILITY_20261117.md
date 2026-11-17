# TITAN microcapital public feasibility prefilter

Research only; no credentials or trading endpoints.

The main execution code's guarded defaults are a 20% equity notional cap, a 5% equity margin cap, and fixed 20x leverage. With 4.14 USDT, the indicative notional budget is min(4.14*0.20, 4.14*0.05*20) = **0.828 USDT**.

Run using a GitHub runner or other network-enabled Python 3.12+ host:

    python -m trading.okx_microcapital_feasibility --equity 4.14 --leverage 20
    python -m unittest research_tests.test_okx_microcapital_feasibility

Fetches **public** OKX SWAP instruments and tickers; supports only explicitly linear USDT-settled SWAPs with base-denominated contract values and live status. Reports minimum contract notionals, rounded to lot sizes, without placing orders.

**A 'within_budget' result is not trading authorization:** Account-level contract limits, current order precheck, fees, spread, liquidity, margin maintenance, and price movement must still be checked. No market position is free from loss or liquidation risk. Existing V1–V5 research does not establish positive net alpha. Do not use this module to arm trading.
