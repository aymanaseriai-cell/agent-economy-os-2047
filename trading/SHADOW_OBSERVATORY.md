# QUANT2037 Shadow Observatory — prospective, public-only decision science

This is not another indicator and not a profit-generating "quantum AI."
It addresses the real missing capability: learning whether each original
six-specialist/seven-quant role and veto improves actual future prediction,
including the opportunity cost of WAIT. The existing risk gates,
NVIDIA advisory and all live trading remain unchanged.

## What it adds

1. Ex-ante decision evidence: every analyzed market produces a SHA-256
   canonical snapshot with original LONG / SHORT / WAIT, six core vote
   summaries, seven quant vote summaries, veto reasons, approximate
   stop/target, source scan SHA-256 and timestamp. The original raw
   research report is also archived, now for 30 days. A SHA-256 digest
   checks changes, but is NOT an independently anchored notarization.
2. Outcome delayed scoring: independent read-only auditor measures
   1h and 4h horizons only after underlying completed 15m bars exist.
   Entry is first 15m open at or after archived report timestamp, never
   earlier. Uses original stops/targets, stop-first ambiguity and
   modeled taker fee/slippage/funding debit. Hypothetical unlevered
   notional returns only, NOT actual fills.
3. Decision abstention accounting: WAIT is not misrepresented as a losing
   trade. Its hypothetical absolute market movement and root blockers
   are recorded as separate diagnostics.
4. Independence firewall: same-asset signals within four hours are tagged
   as correlated repeats, shown but excluded from primary aggregates.
   Missing candles or changed snapshots cause errors, never wins/losses.
5. Anti-cherry-picking archival sampler: predeclared rule selects earliest
   successful public research scan per fixed two-hour UTC bucket,
   regardless of future outcome. Bounded sample, not exhaustive.
6. Policy-version firewall: a SHA-256 fingerprint of the exact 6-agent
   and 7-quant Python decision source modules is saved per scan.
   Primary evidence is restricted to the most recent decision-policy
   fingerprint. Changing the code cannot silently mix old wins or losses
   with a new version's evidence.
7. Evidence threshold: until 100 matured non-overlapping episodes across
   at least 14 days, status remains INSUFFICIENT_PROSPECTIVE_EVIDENCE.
   Even after, it is REVIEW_REQUIRED_NOT_PROFIT_PROOF. It NEVER enables
   orders or changes leverage/sizing.

## Schedules and permissions

okx-six-agent-council.yml: existing read-only scanner archives
all decisions in a quant2037-shadow-evidence artifact and raw reports.

okx-shadow-observatory.yml: independent three-hourly audit reads prior
artifacts through GitHub's standard Actions READ permission. It uses only
the public OKX market/history-candles endpoint for later prices, then
archives quant2037-shadow-outcomes.

GitHub schedule may be delayed. Artifacts can expire and success-only
history sampling excludes failed research runs (failed scans are explicitly
not represented as successful observations). Not a write-once ledger.

## Reproduction

    python -m unittest discover -s tests -p 'test_shadow_*.py' -v
    python -m trading.shadow_observatory capture --scan reports/okx_six_agents.json --out reports/quant2037_snapshot.json
    python -m trading.shadow_observatory audit --archive-dir reports/shadow_archive --out reports/quant2037_shadow_outcomes.json

In Actions, the auditor invokes GitHub CLI to download preceding scheduled
research artifacts. Historical fills, NVIDIA veto outcomes, exact funding
rates, and order-book snapshots at later times are NOT reconstructed.

LIVE OKX execution remains DISABLED by the user's explicit request.
