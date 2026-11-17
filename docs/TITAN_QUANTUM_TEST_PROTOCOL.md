# TITAN Ω — quantum research gate protocol

Applies to the repository's default CI workflow on pushes, pull requests,
nightly scheduled runs and manual test runs as soon as this file lands on main.

**Goal:** 4.15 USDT -> 9.462 USDT (+128%). The goal is an experiment criterion,
not a forecast, guarantee, or verified account balance.

## Mathematics, not quantum hardware

- Exact **three-qubit (eight complex amplitudes)** classical statevector simulation.
- Unitary RY encoding, three nonseparable pairwise ZZ interactions, Hadamard
  interference, Born-rule probability projection.
- Locked phase robustness [0.7, 1.0, 1.3] versus the phase-zero ablation.
- A classical probability model must get exactly the **same causal features**.
- Features use only completed OHLC at or before decision index; next candle is
  the earliest eligible entry. Future bars are never accessed for a signal.

## Evidence requirements for every candidate paper strategy

Use the reusable API \`trading.titan_quantum_gate\`:

1. Supply precommitted OHLC hashes and the exact 4.15/9.462 targets.
2. Compare a quantum candidate and an identical-input classical control.
3. Use chronological 60% training + 20% holdout 1 + 20% holdout 2.
4. For every segment and model, report **ordinary** and **stress** fees/slippage.
5. Account for actual simulated **closed** equity, fill count, ruin, and max DD.
6. Never label floating wick highs or open-position PnL as realized gains.
7. Compare outcomes after fees, with frozen strategy parameters; no peeking at
   held-out returns to select instruments, model thresholds or leverage.
8. Treat any apparent +128% paper success as a **candidate for new prospective
   validation only**, never a live trade record or a reason to increase leverage.

### CI scope and limit

\`.github/workflows/ci.yml\` now runs this quantum gate on each of its triggers.
A passing CI run proves the **math and evidence validator operate**; it does
not prove a trading edge. Other GitHub workflows not using this CI workflow
must explicitly add the gate before their own research executions. There is
no physical quantum processor, no private OKX API and no orders in the gate.

**Stop condition:** No live promotion until robust independent out-of-sample
net performance and paper-to-exchange reconciliation are verified. The user
can still lose all margin using high leverage.
