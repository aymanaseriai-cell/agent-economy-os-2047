# TITAN Omega24 — Causal Hamiltonian PhaseWalk (paper research only)

Branch-only 24h research: 4.15 USDT -> 8.30 USDT (+100% after model fees), 10x–100x only when public contract leverage cap permits. NO real orders, credentials, account endpoints, scheduled workflows, or changes to main/live execution.

## Prior evidence examined
- V5 GENESIS rejected three hypotheses; 828 verified public funding settlements, 206 paper accounting records audited, no fresh independent final.
- Infinite12 verified rerun: 640 cost/model window evaluations, 4,658 paper fills, 11 OHLC proxy liquidations, **0/640** +100% targets. Its best development model/cost/window was +28.90356%, not independent.
- Quantum Forward 128 is an immutable future-signal research study at +128% goal, not a proof of success; historical 6+7 archived signals had 6/6 negative 1h net results.

## New mathematical constructions
1. **Causal Hamiltonian PhaseWalk.** Given 32 lagged completed log returns, estimate volatility sigma, 8-bar normalized momentum m=tanh(sum(r[-8:])/(sigma sqrt(8))), spectral low-frequency response s and 3-bin Dirichlet-smoothed Jensen-Shannon regime divergence J. Define H=[[m,kappa],[kappa,-m]], kappa=0.28+0.16 tanh(s), omega=sqrt(m²+kappa²). Evolve CPU state psi=(sqrt(p),i sqrt(1-p)), p=clip(0.5+0.38m,0.05,0.95), via U(tau)=cos(omega tau) I - i sin(omega tau) H/omega. Verify norm=1. Readout signed Born probability with a fixed trend correction; abstain under regime divergence. This is a new experimental combination, **not** verified original world-first discovery or physical quantum advantage.
2. **Fisher-Bayes Regime.** Dirichlet-smoothed directional posterior from 24 completed returns, Fisher-scale confidence using sqrt(p(1-p)/n), with JS regime veto. A separate causal mathematical competitor.
3. **Classical Momentum.** Reuse original 12h study baseline exactly from trading.titan_omega_infinite12_models.

## Locked evaluation
- One public OHLC collection via original 12h collector; 4 fixed USDT swaps BTC,ETH,SOL,XRP, 1000 completed 15m bars each. Validate source SHA and fixed chronology.
- Disjoint **96-bar = 24h** windows, initial warmup at candle 33. Every eligible window is evaluated, regardless of profit. Reset 4.15 for each window, settle trades before end.
- Each market's earliest 60% of windows is training; latest 40% is chronological holdout. Pick model only by training *stress average closed equity*, then inspect holdout. **All these historical dates have been previously exposed by TITAN research, so chronological holdout is not truly fresh independent validation.**
- Position margin <= 25% of previous closed balance. Leverage min 10, max 100 and no greater than publicly published instrument cap; missing cap/lot/contract metadata leads to no order. Notional <=0.1% prior candle USDT quoted volume. Floor contract sizes to minSz and lotSz. No floating profit compounding.
- Base: 5bp taker + 5bp assumed price impact/slip each way, assumed 1bp funding per 8h when no public realized funding event matches the holding interval. Stress: 15bp taker +20bp slip each way, 5bp/8h proxy. These are not actual user fee tiers.
- Stop before time exit if OHLC adverse excursion crosses stop; liquidation before stop if both crossed. Conservative OHLC proxy liquidation forfeits at least isolated position margin. **Actual historic mark/index-price markouts, exchange tier MMR and L2 orderbook are not reconstructed.**
- Independent ledger auditor verifies ALL windows (including losers), costs, quantity, leverage, funding source, closed equity, timeframe, and train-only selection. Tampering and future mutation tests must fail/leave past signals unchanged.

## Reproduce
Run unit tests:
python -m unittest discover -s tests -p test_titan_omega24.py -v

Then collect:
python -m trading.titan_omega_infinite12 collect --out research_artifacts/omega24_original_okx.json --limit-bars 1000

Run all windows:
python -m trading.titan_omega24 --input research_artifacts/omega24_original_okx.json --out research_artifacts/omega24_all_development.json

Independent audit:
python -m trading.titan_omega24_audit --input research_artifacts/omega24_original_okx.json --report research_artifacts/omega24_all_development.json --out research_artifacts/omega24_integrity_audit.json

GitHub Actions runs **once** on branch push or explicit manual dispatch. Source datasets/ledgers are attached as expiring Actions artifacts; passing tests proves code integrity only, never +100% profitability or independent prospective advantage.
