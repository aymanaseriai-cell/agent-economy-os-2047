# TITAN 2037 leverage and multi-position research

This program evaluates every integer leverage 10x to 100x, tests up to ten simultaneous PUBLIC-signal research candidates, and can simulate a 100% equity margin deployment (default). It NEVER trades.

Each candidate must pass original SURVIVAL-8 research filters. Leverage depends on a cautious stop-distance and assumed-cost proxy, and may abstain if even 10x is too aggressive. Unused capital is not force-invested when no candidates qualify.

The simulator splits hypothetical margin evenly and models adverse simultaneous 0.5%, 1%, 3%, 5%, and 10% market moves on all positions, irrespective of their direction. It shows hypothetical gross loss fractions and flags where isolated margin might already be exhausted. Real liquidations often occur earlier. It does not model OKX contract leverage caps, maintenance tiers, real liquidation prices, funding, liquidity, future prediction or positive investment return.

100x margin leverage leaves approximately 1% price buffer before initial margin is consumed even without maintenance, fees, or slippage. Full capital deployment and repeated entries can wipe out account equity; no multi-agent or quantum-themed strategy can guarantee no liquidation or reaching millions.

Manual simulation:
python -m trading.titan_portfolio_2037 --report reports/okx_six_agents.json --out reports/titan_portfolio_2037.json --margin-share 1 --max-positions 5

Unit tests:
python -m unittest discover -s tests -p test_titan_portfolio_2037.py -v

Workflow: .github/workflows/titan-survival-research.yml

REAL-MONEY TRADING IS STILL STOPPED. This code cannot alter live leverage, create orders, or force account margin allocation. It is experimental research with no trading credentials.
