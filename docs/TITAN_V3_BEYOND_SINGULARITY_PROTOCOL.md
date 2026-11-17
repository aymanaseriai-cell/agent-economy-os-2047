# TITAN Ω — BEYOND SINGULARITY V3: frozen economic alpha research

**Do not conflate a sophisticated model with verified profitability.**
This is an exploratory read-only study. The high-return target is
+25,000,000% from 4.15 USDT to 1,037,504.15 USDT, a 250,001x multiple.
No real trades or funds moved; no physical quantum hardware used.

## 1. Reproducible scientific autopsy BEFORE creating V3

The previous two original exchange-source archives were re-examined
at each recorded fill, exit reason and currency.

| Evidence | OMEGA V1 | Infinite Frontier V2 |
|---|---:|---:|
| Final return after modeled costs | -51.76302% | -57.92167% |
| Trades in selected/diagnostic final ledger | 34 | 20 |
| Winners / all | 9/34 (26.47%) | 7/20 (35.0%) |
| Direction correct 4h after entry | 10/34 (29.41%) | 10/20 (50.0%) |
| Direction correct 24h after entry | 13/34 (38.24%) | 9/20 (45.0%) |
| Gross USD before costs | -2.04419943 | -2.00493108 |
| Transaction fees USDT | 0.13007213 | 0.262136 |
| Net funding cost, measured + proxy | -0.026106 | -0.010504 |
| Adverse liquidation PnL correction | 0 | about -0.14718 |
| Stop-triggered | 30/34 | 9/20 |
| Approx liquidation events | 0 | 3/20 |

The market-direction quality was too weak to survive execution.
V1 4h signed directional markout hit only 29.4%, so simply changing
stop orders cannot establish positive expected value. In V2
directional markouts are close to coin-flip. Gross negative PnL
BEFORE fees in both tests demonstrates lack of economic edge.
Currency contributions were concentrated (V1 BICO about -1.099,
V2 DASH about -1.693) but other symbols lost too.
These are after-selection descriptive diagnostics, not a causal
attribution or independent confidence interval. True L2, past tier
changes and historical mark-price liquidation remain unavailable.

The archived forensics was performed locally on V1 and V2 original
OHLCV ZIP archives and produces the source-hashed JSON and full
individual trade audit CSV in the finished report bundle. Both
archived old systems used overlapping 2026 market calendars;
future testing should not reuse their previous final dates as
unseen evidence.

## 2. Economic hypothesis discovery, not renamed legacy indicators

V3 has EIGHT new hypotheses explicitly implemented in
trading/titan_v3_alpha_discovery.py. All operate on true
completed 4h OHLCV made from 15m OKX price/quote-volume originals.
For t, r_asset and r_basket are 4h log returns; sigma denotes own
historical return standard deviation, ATR range scale; V denotes
the log ratio of exchange quote turnover to its previous 30 bars.

  1. Cross-market spillover: x=(lagged basket log return)/sigma.
     Test if causal-in-time market shocks propagate to followers.
  2. Residual mean reversion: x=(r_basket-r_asset)/sigma.
     Test if relative overshoots revert after liquidity impacts.
  3. Crash aftershock: x=-sign(r_lagged)max(0,abs(r_lagged)/sigma-1.8).
     Test post-jump reversion / trapped selling, not unconditional trend.
  4. Passive volume absorption proxy: x=-(body/ATR)max(0,V)wick_fraction.
     Test high-volume small-body absorption. NO genuine L2 inferred.
  5. Volatility repricing: x=-(body/ATR)max(0,range/ATR-1.5).
     Test transient extreme volatility overshoot and subsequent reversal.
  6. Failed breakout: x=-sign(previous candle body) when previous
     candle tests a prior high and current completed bar re-enters range.
  7. Cross-sectional dispersion: x=(r_basket-r_asset)/dispersion.
     Test panic relative performance conditional on market heterogeneity.
  8. Price-volume decoupling: x=-(r_asset/sigma)max(0,V)
     max(0,wick_fraction-.5). Test failed high-volume price movement.

Classical time-series momentum and always-flat are BASELINES.
There is no pretense of causal identification by intervention.

Training-only ridge slope:
beta_h = SUM(x_h * log(next_4h_close/next_4h_open)) /
         (25 + SUM(x_h^2))
The upper 30% of absolute TRAIN x activates candidate signals.
Prediction sign is sign(beta_h*x_h); insignificant forecasts abstain.

Falsification BEFORE final: withheld 25% DEVELOPMENT candidate
entry/returns, subsampled to <=1 candidate per symbol per UTC day,
week-block signflip against zero after 0.26% log transaction cost
proxy, Holm correction over all 9 predicted hypotheses.
Require adjusted p<=0.10, at least 12 development signals, six
different 7-day blocks, positive after-cost discovery estimate.
A candidate must also pass realized simulated development profit
under both STRESS and EXTREME fees/slippage, >=8 executable
fills, <=30% closed PnL drawdown, and positive stress PnL in
both two distinct development halves. If NO candidate passes,
DO NOT TRADE; final returns of rejected models are not opened.

## 3. Freeze and original exchange data

Before any V3 return fetching, GitHub Actions locks code on the
research branch and hashes an identifier + public contract IDs.
Predefined cohort: 8 NOW-LIVE old USDT swaps excluding all
V1/V2 coins used in this comparison, selected without prices.
210 full days of original completed OKX 15m OHLCV and actual
volCcyQuote, not synthetic quotes; 8*~20160 market rows if
available. Actual market/funding rows preserved in gzip with
SHA256 and current public instrument snapshot. Missing any 210d
continuous panel triggers FAIL, no fallback to shorter/friendlier
dates or alternative profitable symbols.

Source public exchange endpoints:
 https://www.okx.com/api/v5/market/history-candles
 https://www.okx.com/api/v5/public/funding-rate-history
 https://www.okx.com/api/v5/public/instruments

35% FIT, 25% DEVELOPMENT, 40% FINAL, 2d embargo between
windows and near independent final windows. The FINAL code is
predeclared to evaluate ONLY the selected strategy (if any),
plus predeclared simple momentum 2x and zero-exposure control.
No post-final tweaking, no unselected winning model claim.

## 4. Capital, execution and falsification

Small 4.15 USDT account, at most one position; fractional Kelly
from beta and train residual variance, capped 20% of CLOSED
equity as margin and 4% planned initial stop risk.
Current OKX minSz, lotSz, ctVal and quantity steps enforced.
A proposed position cannot exceed 0.2% of previous actual 15m
quote turnover. Next 15m OPEN only; no signal at a
partial/unclosed 4h bar. Stop first in ambiguous OHLC candles;
1.8*ATR initial stop, 5.2*ATR target, 2*ATR trailing,
25*4h bar max hold. Leverage candidates 2x, 3x, 5x.
Three cost scenarios: ordinary exchange taker+slippage, stress,
extreme. Real funding applies only if actually retrieved; a
conservative separate fixed assumed charge covers missing events.
A price-based LIQUIDATION PROXY is explicitly NOT exact OKX
mark-price liquidation.

Risk of ruin: a 1000-run toy IID bootstrap of development
closed-trade returns over 100 hypothetical trades; 'ruin' set
to equity <=20% initial value. Highly conditional assumption,
not a real-world empirical ruin probability.

## 5. Prevent overclaiming

V3 does NOT implement Neural Hawkes, Neural CDE, deep Offline
RL, causally identified representations, live orderbook execution,
point-in-time leverage tier archive, physical quantum advantage,
or full DSR/PBO. Previous V1/V2/other historical research
already used the same 2026 date calendar, so fresh symbols
cannot establish a genuinely unseen future period.
Even a historically successful candidate requires independently
sealed later timestamps to justify stronger performance claims.

Reproduction from repo root:
  python -m unittest discover -s tests -p 'test_titan_v3_alpha.py' -v
  python -m trading.titan_v3_research --out reports/v3_discovery_evidence.json --raw-dir reports/v3_original_okx_210d --trades reports/v3_all_paper_trades.jsonl.gz --curve reports/v3_frozen_equity.svg

Offline exact verification:
  python -m trading.titan_v3_research --offline --compare-report reports/v3_discovery_evidence.json --out reports/v3_offline_replay.json --raw-dir reports/v3_original_okx_210d --trades reports/v3_offline_trades.jsonl.gz --curve reports/v3_offline_curve.svg

No real orders, no private access token or API credentials needed.
