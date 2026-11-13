# TITAN 2037 Flight Recorder

Seven read-only diagnostic agents, working on actual GitHub Actions logs,
not synthetic exchange market signals.

1. Cadence Observer: actual intervals between decisions, not promises of 5s.
2. Coverage Accountant: screened and deeply analyzed markets, including repeats.
3. Veto Root Cause: repeated reasons for NO_CONSENSUS.
4. Portfolio Witness: last historical position count, not current exchange state.
5. Execution Truth: worker-reported protected entries, not independent fills.
6. Cooldown Auditor: reports what GitHub logs can and cannot prove about reentry.
7. Stop Governor: refuses to enable trading, adjust thresholds or place orders.

The hourly manual/scheduled research workflow retrieves up to eight
completed OKX worker runs using GitHub read-only actions permission.
Only a sanitized summary is uploaded. Raw logs stay on the ephemeral runner.
Missing or expired logs are missing evidence, not positive trade outcomes.
This component has no access to OKX API keys or trading endpoints.

The existing OKX trading workflow and owner settings are unchanged.
The existing 30-second exchange-confirmed cooldown is unchanged.
No guarantees of immediate fills, reentry timing, or trading profits.

Reproduce tests:
python -m unittest discover -s tests -p test_titan2037_flight_recorder.py -v
