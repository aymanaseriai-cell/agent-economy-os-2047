# TITAN 2037 Sentinels — Veto forensics (OFFLINE ONLY)

**Safety invariant:** The user's live OKX bot remains stopped. This module has no exchange credentials, network/API calls, trade order routes, or permission to restart the disabled live execution workflow.

Eight **auditable research agents** address recurring NO_CONSENSUS outcomes:

1. **Chronology Sentinel:** refuses future, non-matured, or pre-decision outcomes.
2. **Independence Graph:** collapses repeated signals from the same symbol in the same 4-hour UTC bucket (different symbols may still be correlated).
3. **Veto Regret Auditor:** shows hypothetical forward net returns of rejected opportunities grouped by recorded veto reason. This is descriptive, not causal evidence for removing any filter.
4. **Cost Reality:** subtracts imported fees, slippage and signed funding in basis points.
5. **Regime Drift Radar:** PSI on a chronological holdout with training-only quantile boundaries and an embargo against overlapping labels.
6. **Tail Shield:** mean worst-decile hypothetical net return after at least 20 independent episodes.
7. **Uncertainty Guard:** deterministic exploratory holdout bootstrap, explicitly not a significance test or profit guarantee.
8. **Governance Council:** at least 100 independent matured episodes over 14 UTC days before referring a strategy to human review; never authorizes or submits trades.

## Evidence schema

The CLI accepts imported evidence only:

    python -m trading.titan2037_sentinels --evidence input.json --out reports/sentinels.json

Fabricated schema illustration (not actual trade data):

    {"as_of_ms":2000000000000,"episodes":[
      {"decision_id":"example-1","symbol":"DEMO-USDT-SWAP","side":"LONG",
       "decision_ms":1900000000000,"outcome_ms":1900003600000,
       "entry":"100","forward_exit":"99","fee_bp":"8",
       "slippage_bp":"4","funding_bp":"1",
       "vetoes":["multiverse_no_positive_net_edge"],"regime":"RANGE",
       "regime_feature":0.32}
    ]}

The importer checks chronology and duplicate IDs but cannot prove that
signal records were immutable before outcomes, or that imported prices match
actual execution. Prospective archival and later observations must be
connected and audited before any scientific inference. Forward returns
are hypothetical and unleveraged, with imported cost assumptions.

The scheduled workflow titan2037-sentinels.yml uses empty evidence by
default and reports insufficient data rather than inventing results.
It has read-only repository permissions and no secret access. It is
independent of the existing live workflow and owner stop switches.

Local tests:

    python -m unittest discover -s tests -p test_titan2037_sentinels.py -v
