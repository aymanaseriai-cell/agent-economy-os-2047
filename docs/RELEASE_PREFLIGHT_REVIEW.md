# Read-only release preflight

The release preflight checks PR #114's current GitHub head, P0 issue #98, independent current-head collaborator reviews and four exact-workflow GitHub Actions results. It ignores unrelated or stale workflow runs and fails closed if the provider's evidence lists are truncated. Its sole purpose is to produce a truthful blocker report for a human reviewer; it never approves release, merges, deploys, sends messages or moves funds.

The archived GitHub Actions JSON reports exact blockers. A green check means the auditor ran; it does not mean production is approved. The auditor always sets production_authorized=false because source parity, rollback safety and independent release signoff require separate proof.

Run from the review branch:
python3 -m unittest discover -s tests -p 'test_release_gate_audit.py' -v
python3 -m automation.release_gate_audit --out reports/release-preflight.json

Review evidence is fail-closed for an unresolved collaborator change request, PR-author self-approval, a newer attempt of the same workflow run, or changed gate/base/state during the audit. Comments cannot erase submitted review decisions. This remains a read-only audit; it neither satisfies independent approval nor closes issue #98.
