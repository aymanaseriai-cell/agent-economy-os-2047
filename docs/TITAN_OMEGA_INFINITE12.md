# TITAN Ω INFINITE12 — PAPER-only mathematical research

Status: implemented prototypes, NOT validated alpha. Start 4.15 USDT, 12-hour windows, target 8.30 USDT, 10x–100x conditional leverage. ZERO REAL ORDERS, no private APIs, no spending, no scheduled tasks. New research branch starts from GENESIS V5 and does not touch main or live workflows.

## V1–V5 prior evidence examined

- V1 frozen final paper return −51.76302%, 34 fills, 30 stop exits. No profitable edge.
- V2 regime-ensemble diagnostic −57.92167%; nonidentical market cohort means no fair ranking.
- V3: 0 of 27 model/leverage candidates qualified, flat policy final 0% after rejecting hypotheses; 12 unit tests.
- V4: verified 197,280 original OKX trade/mark/index source rows, original 2023–2025 calendar consumed; none met after-cost qualification; final policy flat 0%.
- V5: 828 genuine public funding settlements in 2026 for BTC, ETH, SOL; three rejected economic mechanisms; 14 tests and independent SHA audit; no new unseen final.

Source documents inherited from the V5 branch: docs/TITAN_INFINITE_FRONTIER_V2_AUDIT.md, docs/TITAN_V3_ACTUAL_RESULTS_20261117.md, docs/TITAN_V4_ACTUAL_EMPIRICAL_RESULTS_20261117.md and docs/TITAN_GENESIS_V5_EMPIRICAL_RESULTS_20261117.md.

## CPU-only mathematical systems (three proposed hybrid architectures + baseline)

1. Quantum Walk Interference: state psi=(1,1)/sqrt(2), and each of 20 lagged log-returns produces psi_next = D(phi) * R_y(2 theta) * psi, theta=atan(50r), phi=atan(30(r-r_previous)). The signed interference statistic is 2 Re(conj(psi_0)*psi_1), threshold 0.22. Norm conservation is asserted.
2. HyperQuantum Commutator: noncommuting Pauli-inspired observables A=m sigma_x and B=z sigma_z. The signed interaction proxy m*z from the commutator is combined with a spectral trend: score=0.55*m + 0.30*spectral + 0.15*m*z. Entry threshold 0.27.
3. BeyondQuantum Bayesian Hazard Gate: Kalman-like latent return mean and posterior variance updated with innovation-sensitive process noise and a switching hazard. Signal only when abs(posterior_mean) exceeds max(0.002,sqrt(posterior_variance)).
4. Classical momentum: 12-bar and 4-bar causal log momentum normalized by previous 20-bar volatility, identical historical inputs and all execution terms.

All names describe mathematical research constructions, NOT beyond-physics hardware, demonstrated world novelty, true quantum computation, or guaranteed prediction. Full tensor networks, causal treatment effects and trained reinforcement learning are NOT implemented.

## Frozen evaluation protocol

Public OKX 15m completed OHLC/quote-volume, instrument lot metadata and funding events for BTC, ETH, SOL and XRP USDT swaps. Fixed disjoint 48-bar = 12-hour windows, starting at bar 33, no retrospective best-window selection. Begin each window with fresh 4.15 USDT. Decision at latest completed t-1, earliest paper fill at next candle open t. Close all positions before window end; at most one at a time. No open PnL counted.

Dynamic leverage = min(100, published contract cap, max(10,0.06/std(previous20 returns))). Margin <=25% of settled equity. Notional <=0.1% of PREVIOUS completed 15m original quote volume. minSz, lotSz, ctVal and exchange published max leverage must be available; otherwise fail closed / no position. Compounding after each closed fill only.

Ordinary model costs: 5bp taker and 5bp assumed spread+slippage PER SIDE. Stress: 15bp taker and 20bp spread+slippage PER SIDE. Apply original public realized funding events when present; otherwise a labelled assumed financing reserve of 1bp/8h or 5bp/8h, proportional to hold time. All ledger fields are archived; negative financing cost from actual observed funding is permitted and labelled.

Liquidation and stops are approximations from trade-candle OHLC, priority assigned to possible liquidation when both are crossed. Proxy maintenance margin is 0.5%. Exact historic mark-price liquidation, L2 book depth, actual fills, fee tiers, historical tiers and synchronized spreads are NOT known. Do not claim actual exchange precision or measured liquidation probability.

## Independent audit and scientific boundaries

Independent module trading/titan_omega_infinite12_audit.py imports NO model/engine and verifies SHA256 input identities, chronology and 48-bar boundaries, lot rounding, leverage, margin, previous quote volume cap, fee arithmetic, gross/net/funding identities, and compounding only after closing. The fee-tamper regression test must be detected. SHA verifies internal integrity, not an exchange signature.

All 2026 dates overlapping V1–V5 and other TITAN studies are already exposed, so these are **DEVELOPMENT** replays only. A fresh, model-frozen PROSPECTIVE test after the research freeze is required before reporting independently verified returns. Independent best return, independent 100% hit-rate and actual liquidation probability are **not measurable** at current evidence level; development hit counts are merely descriptive.

## Execution

1. Run: python -m unittest discover -s tests -p test_titan_omega_infinite12.py -v
2. Collect: python -m trading.titan_omega_infinite12 collect --out research_artifacts/omega12_original_public_prices.json --limit-bars 1000
3. Replay: python -m trading.titan_omega_infinite12 replay --input research_artifacts/omega12_original_public_prices.json --out research_artifacts/omega12_all_development_windows.json
4. Audit: python -m trading.titan_omega_infinite12_audit --input research_artifacts/omega12_original_public_prices.json --report research_artifacts/omega12_all_development_windows.json --out research_artifacts/omega12_independent_audit.json

Workflow .github/workflows/titan-omega-infinite12-paper.yml uses branch push or manual dispatch, never a timer, never a trade endpoint. Original datasets and full ledgers are GitHub Actions artifacts (not oversized source-control commits).
