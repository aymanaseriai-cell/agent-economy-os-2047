# TITAN Quantum +128 — precommitted forward research

The mathematical target is a hypothetical **4.15 USDT → 9.462 USDT (+128%)**.
No real-money trading is permitted in this research code. A positive test is
not a real account profit, nor a guarantee of repeated returns.

The study captures an immutable GitHub Actions artifact with the source run
ID, commit hash, 97 completed public OKX 15-minute candles for each fixed
market, a SHA256 hash per market, and three **same-input** forward signals:
a classical simulation of 3-qubit phase interference, a zero-phase
ablation, and a conventional baseline.

The hypothetical entry occurs at least one full 15-minute interval AFTER
the capture. The shadow evaluator will score the original frozen predictions
on 1-hour and 4-hour fully matured future OHLC (no retuning, no peeking).
For each model, assumed ordinary/stress costs are included and the same
six equal 10%-equity margin allocations at hypothetical 3x leverage apply.

**Limitations:** this is not actual exchange execution, not physical quantum
hardware, not a reliable liquidation/mark-price/funding/orderbook simulator,
and one sample is statistically insufficient to infer trading profitability.

The SHA256 commitment checks accidental or unauthorized editing but does
not provide a digital signature. The GitHub capture-run timestamp and
artifact are needed to verify chronology. Artifacts expire after 90 days.

The repository CI is separate. This research workflow runs once on matching
push, or on explicit manual dispatch. It does NOT add an hourly monitoring task.
To score, manually dispatch with phase=score and the original capture_run_id
AFTER the score_not_before entry+4h timestamp. Early or incomplete data fails.
