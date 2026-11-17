# TITAN Q7: real historical test of FOUR separate +128% replications

**Question:** Can an invented quantum-inspired 6-qubit crypto strategy turn
$4.15 into $9.462 (+128%) *repeatedly*, not once? We do not assume yes.

Different model from Q4/Q5/Q6: a 6-qubit 64-complex-amplitude statevector
with two coupled interference layers, cross-asset 4h breadth, 4h price
momentum (3 and 18 bars), short vs medium EMA, 4h relative volatility
and candle-body pressure. Uses exact completed UTC-aligned 4h OHLC to
decide, then next 15m OHLC for simulated order execution. Born measurement
produces a directional probability. All phase constants, feature gates,
stop/cost assumptions and exits are fixed *before* historical replay.
Compare phase-zero ablation, classical same-feature control and classical
breakout on the *same* markets and paper execution costs.

**Precommitted success criterion:** choose only by first 60d training
(with positive ordinary and stressed net profit, >=5 paper fills, <=35%
drawdown), then require +128% CLOSED equity in **all four disjoint
~30-day holdout periods**, both ordinary and stress costs, and in the
combined 120d run, with <40% stressed drawdown per holdout. Any other
strategy's retrospective single positive period cannot count as proof.

The six OKX USDT swaps are selected using SHA256 of a fixed study name
and public instrument identifier only, on a new named universe explicitly
excluding previously tested market baskets. Real completed 180-day
15-minute candles are archived and hashed by instrument. Margin, public
minSz, lotSz, ctVal; 3x/10x paper leverage, assumed fees/slippage/funding,
conservative OHLC stop-first logic and approximate liquidation are modeled.

The historical OHLC are real; paper fills are NOT exchange execution and
mark-price liquidation and exact funding are not reconstructed. There is
no physical quantum computing hardware and NO LIVE ORDERS. Even a successful
backtest cannot promise live, repeatable returns. Multiple historical
experiments on the same date present selection bias. A failing criterion
means no demonstrated repeated +128% historical edge here.
