# TITAN Ω — INFINITE FRONTIER V2: reproducible research, not live trading

This branch is isolated from main. No user trading account or credentials
are accessed. Return target = +25,000,000% = $4.15 → $1,037,504.15.
The original OMEGA 25M study failed at **-51.76302%** outside development.
Review of its frozen selected 34-trade ledger found **30 stop-triggered exits**
and **9 profitable trades**. Its gross PnL before fees/funding was
**-2.04419943 USDT**, fees **0.13007213 USDT**, funding observed
**-0.02766122 USDT** (net credit), assumed **+0.00155505 USDT**.
BICO contributed -1.09868 USDT net, but other coins also lost.
Development won 8/10 trades, final 9/34: this is a change in predictive
edge/regime, not a loss explained by execution costs alone.

## Implemented mathematically distinct Gen2 families

| New genuinely implemented approach | Real equation/operation | Hypothesis | Data | Compute | Falsifier |
|---|---|---|---|---|---|
| Kalman Bayesian state-space | x_t=φx_(t−1)+η; y_t=x_t+ε; K=P/(P+R) | Stable low-noise trend can be separated from observation noise | Completed 4h returns | O(TN) | 3 OOS stressed returns ≤0 |
| Duration HSMM | p(z_t,d_t | y_(≤t)), h(d)=min(.6,.015+.004d) | Regime survival time adds signal beyond moving averages | Completed 4h returns | O(48TN) | Worse than classic after costs |
| Koopman EDMD/ridge | θ=(XᵀX+25I)⁻¹Xᵀr ; r̂=θᵀ[1,m,M,T,v,mT,Q] | Predictive linear dynamics in nonlinear lifted coordinates | Completed 4h OHLCV | O(n·7²) fit | OOS calibration / net edge absent |
| BOCPD | p(r_t|y_(≤t)) ∝ hazard × likelihood × p(r_(t−1)) | Structural breaks have different hazard-sensitive returns | Completed 4h returns | O(32TN) | False positives overwhelm costs |
| Split conformal | q_(0.9)=Quantile(|r−r̂|) on DEV | Refuse weak forecasts inside empirical uncertainty bands | Dev labels; no final | O(NlogN) | OOS risk/no profitability |
| Distributionally robust forecast | edge=max(0,|r̂|−1.25σ−transaction cost) | Lower-bound forecast survives parameter uncertainty | Train residuals | O(TN) | Zero implementable trades or negative OOS |
| Regime-selective ensemble | score=mean(EDMD,Kalman,HSMM) if concordant & low BOCPD | Abstention helps across transitions | OHLCV | O(TN) | Worse than classic after costs |
| Quantum-inspired unitary phase mixer | complex amplitude |ψ〉→e⁻ⁱHδ e⁻ⁱXβ|ψ〉, 3 qubits; max Born amplitude asset | Phase interference could rank risk-adjusted assets | EDMD + OHLCV | Exact enumeration of identical objective does better |
| Classical exact optimization | argmax_i utility_i including abstention | A fair baseline should beat a heuristic on same objective | Same utility | O(7) | Not a standalone alpha predictor |
| Classical baseline | 0.6T+0.4m | Inexpensive momentum can outperform complexity | OHLCV | O(TN) | Classical outperforms experimental models |

The annealer does **NOT** use a physical quantum computer. It is a
unitary phase-and-mixer mathematical simulation on a CPU. For the same
one-position objective exact exhaustive enumeration is actually
optimal; any improvement in historical PnL must be separately
attributed to different trades, not an optimization guarantee.
Most implementations are research approximations and are not
neural deep learning or verified causal inference.

## Other requested 20-family candidates: status, not fake completions

- Neural Hawkes: requires timestamped trade tape not in original OHLCV.
- Neural Controlled Differential Equations: not fitted; requires neural
  differential solver and predeclared development budget.
- Deep risk-constrained RL and Offline RL: not fitted or tested;
  off-policy coverage and trustworthy action support are absent.
- Causal representation learning: not established; no intervention or
  identified causal structure in observational bars.
- Optimal transport distribution adaptation: not implemented, would
  require regime-conditioned source/target distributions independent of final.
- True option volatility surfaces: absent; must not synthesize IV.
- True historical L2 order book: absent; use raw quote volume only.
- Deep multi-agent policies and meta-learning: not deployed, as baseline
  action-quality evidence is insufficient.
- Market regime switching portfolio MVO: not implemented beyond one
  concurrent position. Funding and maintenance/mark-price histories
  are not sufficiently observed for an institution-grade portfolio engine.
- Advanced neural probabilistic forecasting, full PBO and calibrated
  Deflated Sharpe: not asserted without the requisite data and folds.

## Execution and adversarial protocol

* Fixed random hash of public instrument IDs selects six NOW-LIVE
  previously untested symbols excluding the original six BEFORE
  downloading any price data. **Survivorship bias still remains**.
* Download original OKX 15m OHLCV with volCcyQuote, SHA256 archive and
  public funding observations. Current lot/minSz/ctVal used; past specs
  and historic maintenance tiers not available.
* 35% causal training, then 15% development for calibration and
  model/lev selection, each divided with ~two-day purge+embargo.
  Remaining 50% has three disjoint date spans plus combined span.
  **No final labels ever used to tune prediction or choose winner**.
* 10 models × 3x/10x × 6 splits × 3 cost cases = 360 complete
  paper strategy evaluations; ordinary, stressed and extreme costs.
* Event-based next-real-15m-open fills, stops before take profit,
  a conservative cap of 1% of the previous real 15m quote turnover,
  minimum quantized contract sizes, at most one open position,
  compounded CLOSED equity only.
* **Cannot claim exact exchange execution**: no synchronized
  historical mark price, maintenance margin tiers, L2 depth or
  maker queue; assumes taker execution, uses OHLC liquidation proxy,
  assumed funding where public data unavailable and fixed
  market impact. Closed drawdown omits unrealized excursions.
* Market/calendar multiple-testing persists across prior experiments.
  A high return from retrospectively best final candidate is NOT
  evidence that model was validated. Declared objective +25M% remains
  a hard target in independent holdouts, not training.

## Reproduction
python -m unittest discover -s tests -p 'test_titan_frontier_v2.py' -v
python -m trading.titan_frontier_v2_research --out reports/frontier_v2_result.json --raw-dir reports/frontier_v2_raw_okx --curve reports/frontier_v2_curve.svg --trades reports/frontier_v2_all_paper_trades.jsonl.gz

After the raw files are frozen:
python -m trading.titan_frontier_v2_research --offline --out reports/frontier_v2_offline_replayed.json --raw-dir reports/frontier_v2_raw_okx --curve reports/frontier_v2_replayed.svg --trades reports/frontier_v2_replayed_paper_trades.jsonl.gz --compare-report reports/frontier_v2_result.json

No real orders, no physical quantum computer, and no guaranteed gains.
