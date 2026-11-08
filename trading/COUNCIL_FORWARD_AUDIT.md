# TITAN QUANT2037 council historical proof (no trades)

This module scores actual GitHub-archived, ex-ante 6-agent + 7-quant-filter
research labels against subsequently observed exchange market candles,
NOT against reconstructed/hypothetical past council votes.

It does NOT authenticate to OKX, run NVIDIA, or open orders. No profit is
established from the sample. **Six of six** one-hour hypothetical outcomes
were negative after explicit cost assumptions, on only three symbols.

Read: reports/actual_council_forward_20261108.md.

To reproduce from immutable frozen source:

    python -m unittest discover -s tests -p test_council_forward_audit.py -v
    python -m trading.council_forward_audit --base reports --out reports/replay_actual_council.json

Only research. Trading workflow remains disabled.
