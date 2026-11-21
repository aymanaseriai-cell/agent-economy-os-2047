# Synthetic four-verdict handoff evidence fixture (v1.1)

External technical feedback: [zambodotdev's independent review](https://github.com/Circadian-agent/agent-collective/issues/1#issuecomment-7057165716) and [follow-up pinned-commit review identifying the extra mismatch edge case](https://github.com/Circadian-agent/agent-collective/issues/1#issuecomment-7057386495). v1.1 corrects the wording flaw in v1.0: an agreeing synthetic snapshot digest **does not prove real-world source freshness**. Four separate claims are reported. Synthetic snapshot integrity is a diagnostic, **not** a freshness verdict.

## Exact independent reproduction

Python 3.10+, standard library only; no credentials, network, keys, wallet, or payment:

~~~bash
python3 fixtures/handoff-claims-v1/verify_handoff_claims_v1_1.py
python3 -m unittest discover -s fixtures/handoff-claims-v1 -p 'test_handoff_claims_v1_1.py' -v
~~~

To reproduce fixed content, check out the **commit SHA** linked by the project before running. The runner exits 0 only if every test matches, nonzero on mismatch/invalid fixture.

## Four separate claims

- `saved_integrity`: PASS/FAIL for exact UTF-8 bytes vs **supplied** saved_digest; PASS does not prove who created the digest.
- `current_freshness`: ALWAYS UNVERIFIED_SOURCE_FRESHNESS. This suite **never** fetches a live source. `diagnostics.current_snapshot_integrity` separately reports the synthetic current byte/digest check.
- `independent_anchor`: FAIL if a supplied reference is present and **either** (a) saved bytes do not match their declared `saved_digest`, **or** (b) that declared digest does not match the supplied `anchor_digest`. This is a fail-closed check of the *composite saved claim*, not a comparison of the reference to raw bytes alone. Otherwise NOT_PROVEN because this fixture does not authenticate the reference's custody, origin, immutability, signature or time. A matching reference **is not** a trustworthy external anchor by itself.
- `alias_uniqueness`: PASS/FAIL for POSIX **lexical** path aliases only. `positive.json` and `./positive.json` collide. Symlinks/hardlinks, races, and filesystem-specific equivalences are outside scope; the project's separate [filesystem verifier](../../verifier.py) handles resolved path aliases.

Ten synthetic scenarios: baseline, Tamper A, Tamper B, Tamper B against a contradictory reference, alias collision, altered current snapshot bytes, matching but untrusted reference, unsafe relative path, identical duplicate path, and reviewer-supplied case where a reference digest matches the modified raw bytes but contradicts the still-declared saved digest.

No aggregate security verdict, live freshness, independent provenance, task execution, contract, legal virtual-asset collection, buyer acceptance, revenue, or transfer evidence is asserted. Test vectors remain research candidates, not an acceptance by ProbityAI or a certification.
