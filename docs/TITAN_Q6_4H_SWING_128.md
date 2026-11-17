# TITAN Q6: 4-hour regime quantum swing, 15-minute actual OHLC paper fills

Research goal **+128%** on 4.15 USDT, i.e., 9.462 USDT, not guaranteed.

Q6 is an explicit corrective experiment after Q4 and Q5 failed to show
repeated edge due to short holding periods and substantial fee churn. Q6
uses a **five-qubit simulated quantum circuit** fed five *4-hour causal*
features: 1d and 3d momentum normalized by 4h ATR, EMA trend, volatility
compression, and candle pressure. Only closed UTC-aligned 4h bars generate
signals. Actual completed 15-minute OHLC decides next-bar entry, stop-first
trade exits, 7 ATR profit levels, 2.1 ATR dynamic trailing, and max holding
of 40x4h. No real exchange orders or genuine quantum processor.

Six previously unused live OKX USDT cryptocurrency swaps are frozen via a
hash ranking of public market names prior to reading PnL; current contract
ctVal, lotSz, minSz are enforced on simulated fills with 3x and 10x leverage.
Ordinary and stressed assumed transaction costs and approximate liquidation
are accounted for; no mark-price/order-book history, historical contract
lot changes, or true funding are reconstructed.

Six quantum signal selection hypotheses plus zero-phase and classical
same-feature controls, and classical breakout. Only 50% training data
selects the winner. Two 25% unseen chronological windows and the combined
50% are reported independently. Selection requires positive training
returns in BOTH stress and ordinary scenarios plus minimum three trades.
Any observed +128% requires *closed-paper* target and must hold independently
in BOTH holdouts and BOTH cost models. Post-hoc best returns are diagnostic,
not proof or live-trade authorization.

This is a distinct architecture on different market basket; because
research happens iteratively, later cohorts are not sufficient proof against
multiple testing. Any success still requires prospective confirmation.
