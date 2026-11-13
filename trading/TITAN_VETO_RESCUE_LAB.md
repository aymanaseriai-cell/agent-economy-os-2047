# TITAN 2037 Veto Rescue Lab — missed-trade counterfactuals

Goal: increase **measured legitimate entry opportunities**, not forcibly
buy or sell every 30 seconds. This laboratory evaluates archived,
originally rejected directional *WAIT* decisions to identify which soft
filters may be overly restrictive. It does not change order execution.

Eight research roles:

1. Candidate resurrection: reconstruct original LONG or SHORT core signal
   from a WAIT snapshot, never invent an unrecorded direction.
2. Hard veto isolation: reject any missing derivatives evidence, any core
   hard veto, missing protective stop/target or no named soft veto.
3. Chronology firewall: use the archived policy fingerprint and only
   forward completed public 15m candles after the original decision.
4. Cost stress twin: reprice candidate with 2x taker fees, 3x slippage,
   2x funding assumptions and stop-first OHLC ambiguity.
5. Independent episode filter: avoid repeated same-symbol 4h clusters.
6. Holdout auditor: 70/30 chronological split, with 4h embargo.
7. Uncertainty/tail judge: exploratory bootstrap lower 5th percentile
   of holdout mean net return, no claimed significance.
8. Deployment guardian: only suggests human review after 100 matured
   independent episodes over >=14 UTC days and positive stressed bound;
   **never** changes parameters or enables trading.

Input is public prospective evidence from
`okx-six-agent-council.yml` snapshots and official
public OKX historical 15m candles through the existing bounded API reader.

Run:

    python -m trading.shadow_archive_pull --outdir reports/shadow_archive
    python -m trading.titan_veto_rescue_lab       --archive-dir reports/shadow_archive       --out reports/titan_veto_rescue.json

Unit tests:

    python -m unittest discover -s tests -p test_titan_veto_rescue_lab.py -v

No private OKX API access, no real orders, no dynamic risk loosening,
no guaranteed execution in 30 seconds and no quantum-computing hardware.
This is retrospective hypothetical analysis with known limitations:
selection effects, correlations across symbols, approximate OHLC fills,
modelled fees, and hash-based records not externally notarized.

**Owner stop status preserved:** The existing OKX real-money bot remains
disabled unless the owner separately rearms it in the future.
