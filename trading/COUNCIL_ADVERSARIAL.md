# Original council signal falsification

This is a reproducible offline forensic test of the **real historical
six-agent + seven-quant original research labels** (6 events, 3 symbols).

Originals lost -0.62312% of traded notional on average after modeled costs,
and still lost -0.46161% with zero costs. A matched opposite-side
counterfactual averaged +0.33618% (not independently tradeable evidence).

Strictly diagnostic. The six NVIDIA advisory votes were not captured, and
therefore the execution gate's decision is unknown.

Read reports/council_adversarial_20261108.md for source timestamps, honest
limitations, event rankings and all assumptions. No trade is placed.

Offline replay:
    python -m unittest discover -s tests -p test_council_counterfactual.py -v
    python -m trading.council_counterfactual --base reports --out reports/new_adversarial.json

Trading remains disabled.
