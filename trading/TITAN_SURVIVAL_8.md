# TITAN SURVIVAL-8: eight public-only research agents

This extension adds evidence integrity, six-agent signal consensus, fee/slippage stress, volatility regime changes, tail shocks, adaptive leverage RESEARCH, portfolio concentration warnings, and out-of-sample testing requirements.

- No OKX credentials or account endpoints; cannot send orders.
- Advisory leverage 1x-8x (not automatically set on OKX).
- Illustrative capital-at-stop budget <=1% equity; stress scenario <=3%; suggested isolated margin <=20% equity.
- These are theoretical model caps, NOT guaranteed maximum losses or liquidation prices.
- No 100% margin obligation; no multi-position deployment without correlation evidence.
- No validated historical advantage, future profitability guarantee, quantum hardware, or guarantee against liquidation.

Manual GitHub workflow: .github/workflows/titan-survival-research.yml.
Test: python -m unittest discover -s tests -p test_titan_survival_council.py -v.
CLI: python -m trading.titan_survival_council --report reports/okx_six_agents.json --out reports/titan_survival_eight.json.

The original live execution workflow remains deliberately disabled. Running SURVIVAL-8 does not enable trading.
