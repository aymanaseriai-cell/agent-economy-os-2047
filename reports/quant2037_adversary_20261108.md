# QUANT2037 original 6+7 council: real-data adversarial twin audit

## Status: engineering validation only; NO demonstrated profit

Frozen public OKX market data captured at 2026-11-08T14:32:32.068036+00:00. The exact original
six-specialist plus seven-quant pipeline was replayed against each
original capture and 11 deterministic, synthetic microstructure mutations.

## Frozen evidence integrity

- Source SHA256: b5f6995fb47ae1af460dc47008c44361dc3aa701e5b1ee7cd93d74d229fc2f64
- Original full public snapshots: reports/quant2037_adversary_raw_public.json
- Full replay and 11 scenarios per instrument: reports/quant2037_adversary_result.json
- No OKX private credentials, orders or positions were accessed.
- Data were obtained from public REST endpoints sequentially, not atomically.

## Observed results

| Instrument | Original council | Mild role changes | Hostile role changes | Mild quant changes | Hostile quant changes | Final flips |
|---|---|---:|---:|---:|---:|---:|
| BTC-USDT-SWAP | WAIT | 0 | 1 | 0 | 3 | 0 |
| ETH-USDT-SWAP | WAIT | 0 | 1 | 0 | 0 | 0 |
| ZEC-USDT-SWAP | WAIT | 0 | 2 | 0 | 3 | 0 |

- Markets analyzed: 3.
- Synthetic attacks performed: 33.
- Model errors: 0.
- Original LONG/SHORT research candidates: 0.
- Total changed final decisions: 0.
- Changed core role vote records in hostile scenarios: 4.
- Changed seven-system verdict records in hostile scenarios: 6.

These raw voting changes often leave final WAIT unchanged; final stability
must NOT be interpreted as trading skill or protection against true spoofing.
No positive candidate was observed in this three-market initial scan.

## Reproduce exactly, no network calls

    python -m unittest discover -s tests -p test_market_adversary.py -v
    python -m trading.market_adversary replay --evidence reports/quant2037_adversary_raw_public.json --out reports/reproduced_adversary.json

Compare reproduced JSON with reports/quant2037_adversary_result.json.
The public inputs are versioned and their SHA256 fingerprint is in
the output. Additional independent GitHub Actions jobs may gather fresh
market data with a different hash and different results.

## Interpretation

Adversarial what-if inputs are manufactured by the tester. They are
not genuine exchange spoofing observations, proof of malicious intent,
true order-book change forecasts or tests of executable orders.
There is no archived historical NVIDIA council vote or financial PnL
in this audit. Live OKX trading remains disabled as requested.
