# OMEGA SINGULARITY: research only +25,000,000 percent

Target from 4.15 USDT is 1,037,504.15 USDT, because multiplication
factor is 250,001. This is an extreme research hypothesis, not a forecast.

## Model family definitions and falsifiable premises

All use completed 4h bars aggregated from ORIGINAL OKX 15m candles and
ten strictly historical features: short m and longer M ATR-normalized
momentum, EMA gap T, volatility compression v, exchange quote-volume Q,
candle pressure P, 24-bar range breakout B, cross-asset breadth b,
up/down fraction u and EMA price distance d. The score changes position
only when |score| >= 0.39. Models 6, 11, 13 fail-closed.

01 Quantum-inspired: q=2P(bit3=1 | RY input, ZZ phase, H readout)-1.
02 Finite path integral: tanh(sum_{x,y in m,M,T} x exp(-|x-y|) /
   sum_{x,y} exp(-|x-y|)). Tests price-path coherence.
03 Nonlinear chaos saturation: tanh(1.7m-0.32m^3-0.3v).
04 Hierarchical Bayes: 2sigmoid(m+0.4T+5 shrinkage_asset_train)-1.
05 Information geometry: tanh((u-b)/(1.01-u^2)+0.25Q).
06 Actual trade-arrival Hawkes: UNTESTED, no individual event tape.
07 Hidden Markov inspired filter: tanh(T(1-0.3|v|)+0.4u).
   Not a fully estimated hidden Markov model.
08 Restricted contextual RL / bandit: tanh(15 training_binned_reward+0.3T)
   with volatility abstention; NOT a trained deep reinforcement agent.
09 Causal invariance SCREEN: momentum-return correlation sign stable
   across three training segments; cannot establish actual causation.
10 Multihorizon representation: tanh(0.4m+0.6M+0.35T), no deep encoder.
11 Historical true order-book imbalance: UNTESTED, no L2 snapshots.
12 Restricted linear genetic programming: population 16, 4 seeded
   generations on training next-bar after-cost proxy; no final tuning.
13 Historical options volatility surface: UNTESTED, no options IV panel.
14 Meta-learning approximation: shrinkage asset posterior from training.
15 Multiagent proxy: nonlinear fusion 0.4 Bayes +0.35 HMM +0.25 SGD.
16 Wavelet-like multiscale contrast: tanh(0.6(m-M)+0.5(M-T)+0.3T).
17 Uncertainty gated expert ensemble: Bayes/SGD/QPU-sim fusion only when
   their pairwise disagreement remains below 0.8.
18 Structural change breakout: tanh(1.6 B+0.3v) when |B|>0.1.
19 Dynamic risk portfolio proxy: tanh((T+0.5M)/(1+|v|)),
   abstains on extreme volume anomaly; max one open asset.
20 Hybrid gated meta-controller: trained Bayes/SGD/genetic/QPU-sim mix,
   suppress high volatility.
21 Classical comparator: tanh(0.6T+0.4m).

All original research model code: trading/titan_omega_25m_families.py.
These are distinct testable approximations, not claims of fully
implementing generalized causal discovery, institutional RL, physical
quantum hardware, exact Hawkes, or a fully estimated HMM.

## Data provenance and limitations
Actual exchange data sources:
https://www.okx.com/api/v5/public/instruments
https://www.okx.com/api/v5/market/history-candles
https://www.okx.com/api/v5/public/funding-rate-history

The original OKX candle arrays, including volCcyQuote and confirm=1,
are stored in gzip JSON. Per-market SHA256 hashes and download UTC
milliseconds are in each run manifest. Funding realizedRate is real only
where the public 3-month endpoint supplies it; earlier funding is an
explicitly marked assumption, NOT fabricated actual funding rates.
Historical mark and index prices, L2 snapshots, matching-engine
latency, contract lot changes and exact maintenance margin tiers were
NOT obtained. Therefore all trade fills and liquidations are
approximate simulation, not a proof of actual historical executability.
Current public contract minSz, lotSz, ctVal are enforced; instruments
selected as currently live causes survivorship bias in the study.

## Research split, optimization and audit
180d 15m original data across six name-hash-selected previously untested
crypto markets, ~103,000 candles in total. First 35% train fits logistic
SGD, genetic vector search, Bayesian shrinkage, contextual bandit;
15% development segment selects one winning model on precommitted
positive return and drawdown constraints, with >=2-day purge at
boundaries. Final 50% three separate holdouts and continuous aggregate
are NOT used to tune model parameters. 18 executable policies X
3x/10x = 36 combinations. Six chronological study periods X ordinary
and stressed fee/slippage scenarios = 432 paper runs.

Execution: 4h completed indicators, next 15m candle open, one open
position globally, 30% equity margin maximum and 12% planned stop,
public contract lot/minimum, ordinary taker fee 0.05% per side and
stress taker 0.08%, nominal slip 0.03% vs stressed 0.1% each fill,
volume-based impact proxy, 1.8 ATR stop, 6 ATR take-profit, 2.3 ATR
trailing, conservative stop before target on candle ambiguity.
Liquidation is an adverse 15m candle barrier proxy NOT mark-price
OKX clearing; no user exchange orders. Recorded funding where
available; 0.01% per eight hours assumed where missing.
Result contains per-period return, fees, funding, liquidation proxy,
trade count and CLOSED equity max drawdown; worst intratrade
drawdown not measurable exactly from OHLC bars.

Falsification: week-level sign flip with 36-hypothesis Bonferroni
adjustment and week-block bootstrap indicative bounds. These are
exploratory, not calibrated proof of statistical significance. Genuine
Deflated Sharpe Ratio and PBO require accurate correlated trial
distributions and more extensive combinatorial validation and are
NOT asserted or silently fabricated. Cross-asset/temporal dependence
and previous strategy experiments persist; final segments in this
one study do not alone prove future profits.

## Reproduction commands
python -m unittest discover -s tests -p 'test_titan_omega_25m.py' -v
python -m trading.titan_omega_25m_engine --out reports/omega_25m_report.json --raw-dir reports/omega_25m_original_okx --curve reports/omega_25m_equity.svg --trades reports/omega_25m_all_trades.jsonl.gz

Zero real orders. Source data and full audit archived as GitHub
Actions artifacts. Artificial synthetic fixtures appear ONLY in
unit tests and are NOT used to claim PnL.
