# TITAN QUANT2037 — adversarial test of **actual** archived 6+7 signals

## Result: FAIL TO PROVE POSITIVE EDGE

The six recorded 6-agent plus 7-quant research labels were published
before the subsequent OKX candle movements used for this one-hour audit.
This study scores the *real original labels*, not a substituted EMA/RSI system.
The NVIDIA advisory layer is **not historically observed**, and these were
research labels, not verified real-money orders.

### Four predeclared diagnostics

1. **Frictionless:** zero exchange fees, zero slippage and zero funding.
2. **Normal costs:** assumed 0.05% taker fee EACH side, 0.03% unfavorable
   slippage EACH side, and 0.01% adverse funding per 8h prorated.
3. **Stress costs:** 0.08% taker EACH side, 0.10% slippage EACH side,
   0.02% adverse funding per 8h prorated.
4. **Opposite-side counterfactual:** identical publication timing,
   inverse direction, same *percentage stop/target distances* on the same
   subsequent 15m bars. This is NOT an independently valid strategy.

Additionally, for each recorded signal, examine **68 completed prior one-hour
windows** (18h lookback, exactly same instrument and indicated direction)
with stop/target distances scaled to each historical entry price.
The placebo OHLC horizons end *before* the respective published signal.
These 408 windows overlap heavily and are **NOT independent observations**;
the ranks are descriptive and do NOT provide a legitimate p-value.

## Result overview (unlevered % of synthetic traded notional)

| Experiment | Mean 1h net result |
|---|---:|
| Frictionless | -0.46161% |
| Original signals, modeled normal costs | -0.62312% |
| Original signals, cost stress | -0.82503% |
| Matched opposite-side hypothetical | +0.33618% |

**Originals beat their hypothetical inverses in 1/6 cases**.
**Median percentile versus pre-signal, same-side placebo windows:** 18.38th.

## Individual recorded events

| UTC report time | Contract | Side | No costs | Normal | Stress | Reverse* | Prior placebo rank |
|---|---|---|---:|---:|---:|---:|---:|
| 2026-11-07 21:25 | ZEC-USDT-SWAP | SHORT | -0.8238% | -0.9860% | -1.1889% | +0.6616% | 1.47th |
| 2026-11-07 21:25 | PEPE-USDT-SWAP | SHORT | -0.3948% | -0.5565% | -0.7588% | +0.2332% | 17.65th |
| 2026-11-07 22:08 | PEPE-USDT-SWAP | SHORT | -0.8793% | -1.0416% | -1.2447% | +0.7172% | 5.88th |
| 2026-11-07 22:47 | PEPE-USDT-SWAP | SHORT | -0.3995% | -0.5603% | -0.7615% | +0.4549% | 30.88th |
| 2026-11-08 00:04 | ZEC-USDT-SWAP | SHORT | +0.0477% | -0.1135% | -0.3150% | -0.2089% | 48.53th |
| 2026-11-08 00:13 | UNI-USDT-SWAP | LONG | -0.3200% | -0.4809% | -0.6813% | +0.1591% | 19.12th |

*Reverse-side diagnostic matches geometric risk and take-profit distances;
it is NOT a recommendation to invert the trading algorithm. Its winning
appearance may be caused entirely by this brief rising market regime.

### Instrument-level dependence

| Unique instrument | Archived observations | Mean original result |
|---|---:|---:|
| PEPE-USDT-SWAP | 3 | -0.71947% |
| UNI-USDT-SWAP | 1 | -0.48087% |
| ZEC-USDT-SWAP | 2 | -0.54973% |

The three PEPE and two ZEC labels overlap in time. Do not multiply
these samples as six distinct profitable/unprofitable trade outcomes.
Even grouping by instrument leaves only THREE asset clusters.

## Known limitations

- Results are based on only six archived qualifying signals, recorded over a
  short interval, and three symbols. They are not prospective multi-month
  or true full-market performance statistics.
- The six core roles and seven quant systems produced these labels at the
  recorded times; the missing NVIDIA review was not replayed or invented.
- Taker fees, slippage and funding are explicit modeling assumptions;
  historical microstructure and actual exchange fills are unavailable.
- The 18h placebo windows share time and price outcomes, and are subject
  to market regime selection; do not derive p-values or predictive confidence.
- The matched inverse trade is an adversarial sanity check only; it does
  not show that flipping the model is profitable in future periods.
- This evidence cannot rule out better performance in other market regimes.
- Full proof requires collecting timestamped RAW book/trade/OI/funding
  snapshots, original 6+7 decisions, NVIDIA vetoes, and observing
  long out-of-sample futures without changing the frozen thresholds.

## Reproduction and safety

The exact archived original-label file and three complete later-candle
datasets are committed in the project alongside this script.
Run WITHOUT API keys, exchange private endpoints, or live trading:

    python -m unittest discover -s tests -p test_council_counterfactual.py -v
    python -m trading.council_counterfactual --base reports --out reports/reproduce_council_adversarial.json

A manual-only offline GitHub Actions workflow verifies report equality and
SHA-256 hashes of all underlying data. The existing real-money OKX workflow
remains disabled and settings stay NO / dry_run.
