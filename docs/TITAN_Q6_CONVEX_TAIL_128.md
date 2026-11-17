# TITAN Q6 Convex Tail — new six-qubit quantum-inspired +128% historical study

Goal: net closed PAPER return +128% on 4.15 USDT to 9.462 USDT.
Trading with leverage is highly risky and real results are not guaranteed.

Improvement over previous Q3/Q4/Q5:
- 6 simulated qubits / 64 complex amplitudes, unitary ZZ phase interference,
  with six independent causal price features and all-phase-ablation controls.
- Three-phase consensus plus Donchian 48/96 bar breakout, volatility squeeze,
  trend filters and explicit abstention instead of forced trade.
- Asymmetric right-tail holding: no forced take-profit cap. Next-open entry,
  2*ATR initial stop, 2.8*ATR trailing stop updated strictly after bar close,
  96-bar maximum holding and liquidation-before-stop on ambiguous candles.
- Real public OKX minSz / lotSz / contract value, fee, stressed slippage and
  assumed funding; 3x/10x paper leverage (NOT permission to trade for real).
- Six crypto markets selected using SHA256 ranking of market NAME and a
  precommitted study ID before downloading any historical prices. Excludes
  Q4/Q5/H128 recent cohorts. OHLC archived with SHA256 manifests.
- 40% chronology train, 3x20% separate holdouts and concatenated 60% holdout.
  Only training-positive quantum policies can be selected. A single
  retrospective winner is disclosed but never treated as a validated strategy.

CAUTION: Six-qubit circuit is computed entirely on ordinary CPU hardware;
not physical quantum hardware, nor demonstrably superior to a classical
baseline. Real OHLC, but hypothetical trade fills. Price OHLC cannot reproduce
order-book liquidity, mark-price liquidation, historical fee tiers or funding.
Repeated historical experimentation increases selection bias. Do not deploy
without prospective risk-limited replication.
