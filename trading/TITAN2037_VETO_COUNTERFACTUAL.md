# TITAN 2037 Veto Red Team — Rejected Signal Counterfactuals

This module tests whether an already-rejected directional hypothesis
(recorded as WAIT) would have hypothetically gained or lost after subsequent
completed public candles, using its ORIGINAL stop and target.

Eight complementary systems:

1. Archived snapshot SHA-256 verification (not independent notarization)
2. Historical pre-recorded directional veto reconstruction
3. Normal, 2x and 3x fee / slippage / funding stress
4. Next-bar-open stop-first and gap-conservative counterfactual replay
5. Per-symbol four-hour correlated-signal deduplication
6. Exact decision-policy fingerprint firewall
7. UTC day block exploratory bootstrap + purged chronological holdout
8. Human-only governance — never authorize live entries

The input is not synthetic: shadow_archive_pull selects predeclared
historical public market decision snapshots, and the Red Team
fetches OKX PUBLIC market history AFTER the original observations.
The source snapshot time and completed candle guard prevent reusing
future candles to invent pre-publication signals.

Limitations: estimated entries, fees and slippage do not establish real
fill prices or executable market opportunity. WAIT is not "missed profit".
No causal veto quality is proved by positive hypothetical results.
SHA-256 alone is not independently witnessed notarization.
100 matured cases over 14 days lead only to review, never automatic
approval or relaxed risk controls.

Run tests:
python -m unittest discover -s tests -p test_titan2037_veto_counterfactual.py -v

Run from downloaded public snapshots:
python -m trading.titan2037_veto_counterfactual --archive-dir reports/shadow_archive --out reports/titan2037_veto_counterfactual.json

The user's stopped live trading, owner stop variables, leverage, orders,
position sizing, risk rules and 30-second verified cooldown are unchanged.
