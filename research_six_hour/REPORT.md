# TITAN Omega | Six-Hour Net +100% | PAPER ONLY

**17 November 2026 UTC. Development research; no independent forward test and no real orders.**

## Core result
47 distinct non-overlapping 6h UTC windows, crossed with 3 signal families, 8 leverages (3x,5x,10x,20x,30x,50x,75x,100x) and 2 fee/slippage scenarios (48 policies), produced **2,256 correlated scenario-window trials** and **8,285 paper fills**. **Zero windows finished with 8.30 USDT or more** from 4.15 USDT after modeled frictions. Do not interpret the 2,256 trial count as independent market sampling.

390 mark-price liquidation *proxies*, affecting 203 trials; 62 trials finished at/below the 0.83 USDT ruin level; 1,688 trial-windows had negative six-hour net returns. These are development estimates, not exchange-confirmed executions.

The adaptive policy withheld orders for 31 later development windows because none of three economic signals showed qualifying positive edge in the earlier development segment. Its 0% return preserves 4.15 USDT; it is not a profitable strategy.

## Evidence inputs
Six USDT perpetual swaps ETH, SOL, XRP, DOGE, ADA, LINK; 3,455 continuous original confirmed 5-minute trade candles and 3,455 mark-price candles per swap (41,460 underlying candle records); 100 realized funding rates each; public current instrument metadata and isolated first-tier leverage/maintenance-margin data. 47 fixed windows cover 2026-11-05 18:00 UTC through 2026-11-17 12:00 UTC. No raw OHLC time gaps. SHA-256 source checks are mandatory.

Signal families: prior completed bar shock continuation, shock reversal and trade-versus-mark price dislocation mean reversion. Entry next bar open, no decisions using target-bar prices; one position at a time; maximum 30-minute hold; stop 0.6% underlying, target 1.2%, exit all at six-hour cutoff. Costs base = 0.05% taker per side + 0.04% slippage + 0.02% spread/impact; stressed = 0.15% taker per side + 0.25% slippage + 0.10% extra per side. Observed settlement funding deducted/credited across holding periods. Contracts quantized by OKX minSz/lotSz/ctVal, ≤45% capital margin and capped to 0.1% of previous bar quote turnover. Leverages 75x/100x prohibited for DOGE, ADA and LINK by current specs.

**Execution limitation:** Historical tick/L2 depth, order queue, real stop-gap fills, exact maintenance tier and liquidation execution, and historical point-in-time contract specs were unavailable. Five-minute mark OHLC cannot reconstruct intrabar order. Liquidation results use a declared conservative *proxy* (priority over stop/take); no assertion of real historical fill or liquidation outcomes.

## Full grid
| Signal | Cost | Leverage | Mean net return | Median | Loss windows | Proxy liq. windows | Trades |
|---|---|---:|---:|---:|---:|---:|---:|
| shock_continuation | base | 3x | -1.567% | -1.614% | 87.2% | 0.0% | 270 |
| shock_continuation | base | 5x | -2.694% | -2.831% | 87.2% | 0.0% | 270 |
| shock_continuation | base | 10x | -5.460% | -5.386% | 89.4% | 0.0% | 270 |
| shock_continuation | base | 20x | -10.655% | -10.688% | 89.4% | 0.0% | 270 |
| shock_continuation | base | 30x | -15.395% | -16.155% | 89.4% | 0.0% | 269 |
| shock_continuation | base | 50x | -25.461% | -27.017% | 91.5% | 6.4% | 264 |
| shock_continuation | base | 75x | -29.766% | -33.189% | 87.2% | 17.0% | 192 |
| shock_continuation | base | 100x | -48.243% | -50.506% | 93.6% | 70.2% | 186 |
| shock_continuation | stress | 3x | -7.349% | -7.273% | 100.0% | 0.0% | 304 |
| shock_continuation | stress | 5x | -12.412% | -11.924% | 100.0% | 0.0% | 304 |
| shock_continuation | stress | 10x | -23.370% | -22.723% | 100.0% | 0.0% | 304 |
| shock_continuation | stress | 20x | -39.639% | -39.153% | 100.0% | 0.0% | 304 |
| shock_continuation | stress | 30x | -51.073% | -51.303% | 100.0% | 0.0% | 304 |
| shock_continuation | stress | 50x | -65.559% | -67.004% | 100.0% | 6.4% | 293 |
| shock_continuation | stress | 75x | -59.763% | -65.878% | 97.9% | 23.4% | 194 |
| shock_continuation | stress | 100x | -66.624% | -76.977% | 97.9% | 85.1% | 180 |
| shock_reversal | base | 3x | -1.039% | -0.915% | 74.5% | 0.0% | 211 |
| shock_reversal | base | 5x | -1.750% | -1.525% | 72.3% | 0.0% | 211 |
| shock_reversal | base | 10x | -3.584% | -3.211% | 74.5% | 0.0% | 211 |
| shock_reversal | base | 20x | -6.962% | -6.263% | 74.5% | 0.0% | 211 |
| shock_reversal | base | 30x | -11.080% | -10.052% | 76.6% | 2.1% | 212 |
| shock_reversal | base | 50x | -18.521% | -15.768% | 76.6% | 10.6% | 206 |
| shock_reversal | base | 75x | -21.213% | -15.531% | 72.3% | 29.8% | 138 |
| shock_reversal | base | 100x | -30.782% | -40.184% | 70.2% | 57.4% | 142 |
| shock_reversal | stress | 3x | -5.742% | -5.469% | 97.9% | 0.0% | 241 |
| shock_reversal | stress | 5x | -9.779% | -9.570% | 97.9% | 0.0% | 241 |
| shock_reversal | stress | 10x | -18.492% | -18.365% | 97.9% | 0.0% | 241 |
| shock_reversal | stress | 20x | -32.005% | -32.683% | 97.9% | 0.0% | 241 |
| shock_reversal | stress | 30x | -42.079% | -43.636% | 97.9% | 2.1% | 240 |
| shock_reversal | stress | 50x | -55.594% | -57.342% | 97.9% | 10.6% | 232 |
| shock_reversal | stress | 75x | -50.720% | -53.059% | 95.7% | 29.8% | 150 |
| shock_reversal | stress | 100x | -56.791% | -59.585% | 95.7% | 78.7% | 144 |
| trade_mark_reversion | base | 3x | -0.295% | -0.053% | 51.1% | 0.0% | 79 |
| trade_mark_reversion | base | 5x | -0.512% | -0.105% | 51.1% | 0.0% | 79 |
| trade_mark_reversion | base | 10x | -0.805% | -0.237% | 51.1% | 0.0% | 74 |
| trade_mark_reversion | base | 20x | -1.214% | 0.000% | 46.8% | 0.0% | 67 |
| trade_mark_reversion | base | 30x | -1.554% | 0.000% | 40.4% | 0.0% | 57 |
| trade_mark_reversion | base | 50x | -2.934% | 0.000% | 34.0% | 2.1% | 46 |
| trade_mark_reversion | base | 75x | 0.656% | 0.000% | 0.0% | 0.0% | 1 |
| trade_mark_reversion | base | 100x | 0.836% | 0.000% | 0.0% | 0.0% | 1 |
| trade_mark_reversion | stress | 3x | -1.904% | -1.256% | 78.7% | 0.0% | 80 |
| trade_mark_reversion | stress | 5x | -3.117% | -2.094% | 78.7% | 0.0% | 80 |
| trade_mark_reversion | stress | 10x | -5.984% | -4.372% | 76.6% | 0.0% | 77 |
| trade_mark_reversion | stress | 20x | -9.842% | -8.258% | 74.5% | 0.0% | 69 |
| trade_mark_reversion | stress | 30x | -12.879% | -9.965% | 68.1% | 0.0% | 66 |
| trade_mark_reversion | stress | 50x | -15.562% | -11.895% | 59.6% | 0.0% | 57 |
| trade_mark_reversion | stress | 75x | 0.245% | 0.000% | 0.0% | 0.0% | 1 |
| trade_mark_reversion | stress | 100x | 0.289% | 0.000% | 0.0% | 0.0% | 1 |

## Statistical integrity
0/47 successes per fixed policy does NOT imply 0% true success probability. A naive iid Wilson 95% upper bound is roughly 7.56% per 47 trials, but day dependence, common prices across policies and post-hoc comparison make that bound unsuitable for a prospective reliability claim. Block-bootstrap development intervals and full trial ledgers are in scientific_summary.json and grid-results.json.gz. In high leverage mark-reversion cases with slightly positive averages, only one trade took place across 47 windows: this is NOT demonstrated positive alpha or repeatability.

## Independent scientific audit
Independent auditor does NOT import engine code and independently checks all source SHA, all 47 starts, 6h cutoff, signal time, contract legality, current tier leverage, margin, prior volume, 8,285 gross/fee/funding/net records, each compounding equity step, mark-price liquidation-proxy triggers and omitted/falsified records. **0 structural faults**. 13 unit and adversarial negative-control tests passed; tampered input and ledger fraud are rejected. The audit is arithmetic/structural only.

## Reproduction
Files: engine.py, auditor.py, tests/test_research.py, manifest.json, grid-results.json.gz, grid_summary.csv, scientific_summary.json and archive titan6h-okx-5m-20261117.zip.

Run:
    python engine.py --data titan6h-okx-5m-20261117.zip --out grid-results.json
    python auditor.py --data titan6h-okx-5m-20261117.zip --results grid-results.json.gz --out audit.json
    python -m unittest discover -s tests -p 'test_*.py' -v

Raw dataset ZIP SHA256: edd0283aaeeb6f1fb7cb7672f3a4690dc18256c41b033e27ff8d9ef60b73bfb8
Grid ledger gzip SHA256: 43ac47caef6921a1c3df608ef0994ec4dec41359abb4c07da1e7effd3b517de6

## Ten-point verdict
1. Net 100% in 6h? NO (0 observed).
2. After costs? NO; both modeled fee+slip regimes failed.
3. Trades to double? Not applicable; none doubled.
4. Maximum drawdown? See each model grid; high-risk scenarios include 100% adverse-equity drawdown proxies.
5. Success? 0/47 per fixed model; 0/2256 correlated trials.
6. Liquidation/ruin? 390 proxy liquidation events; 203 affected trials; 62 ruin trials.
7. Feasible orders? Lot and current constraints passed, but historical execution could not be verified.
8. New independent forward test? ZERO independent observations.
9. Reproducible? Frozen raw sources, all ledgers, stand-alone auditor, 13 green tests.
10. Github? Code and reports reside on this research branch; large binary data and ledgers may require standalone archives.

**Decision: no scientifically demonstrated short-horizon positive-after-cost edge, and therefore no defensible high-leverage live trading claim.**
