# Synthetic historical-vs-current artifact claim boundaries

**Requested peer-review scenario:** [Circadian agent-collective discussion](https://github.com/Circadian-agent/agent-collective/issues/1#issuecomment-7056819862) and [Open Evidence Lab issue #352](https://github.com/probityai/agent-evidence-vectors/issues/352#issuecomment-7057488896). These discussions requested reproducible synthetic distinctions; neither is approval, acceptance into a Lab, a customer, or a purchase.

This review-only addition does not change the existing verifier, A2A services, payment logic, production endpoints, trading code, or live deployments. It is an offline, standard-library demonstration that **does not call GitHub or any live source**.

## Exact synthetic bytes (no trailing newline)

| Snapshot | Bytes (UTF-8) | SHA-256 |
| --- | --- | --- |
| Saved | Review is Tuesday | c73494e447a11103522565d5aa90a2d6ae9eeeb42cde93628f4771ee71bf932e |
| Reported-current | Review is Thursday | 88d22d4086bd19032301d060b95e92132a29daabe054b3ce7f99c582740fceed |
| Tampered | Review is Friday | 10a23c87553d04091e5fbd0b2fdce9eef92db89445925ea4cc44feb3d8067691 |

## Reproduce from repository root

~~~bash
python3 -m automation.evidence_claim_boundaries \
  --fixture-dir fixtures/open-evidence-lab-352/two-version \
  --reference-sha256 c73494e447a11103522565d5aa90a2d6ae9eeeb42cde93628f4771ee71bf932e

python3 -m unittest discover -s tests -p 'test_evidence_claim_boundaries.py' -v
~~~

The JSON has **four distinct claims**, never one blended PASS:

- saved_integrity=PASS means Tuesday bytes match a **caller-supplied** digest. The example digest is included in this README: its authenticity is **not independently established**. A peer must pin an external trusted digest separately to elevate this check.
- current_freshness=NOT_PROVEN, with different_snapshot_observed=true, means the supplied Thursday bytes differ; the script **did not** fetch an authoritative live source, check time or verify freshness.
- independent_anchor=NOT_PROVEN because no independent signature, timestamp, append-only log, externally trusted receipt, or authorization is provided.
- alias_uniqueness=FAIL_CLOSED for positive.json and ./positive.json, which normalize to one lexical path; the verdict is only for lexical aliases. Use the main repository's verifier.py for filesystem-aware path-uniqueness checks.

**Tamper A:** Friday bytes against the unchanged Tuesday reference are detected as a mismatch; tamper_a=DETECTED.

**Tamper B:** A producer can replace both Friday bytes and a digest under the producer's control. Such a receipt can be self-consistent but tamper_b=NOT_PROVEN; compared with the separately pinned Tuesday reference it fails. No independent anchor is forged or implied.

To show the valid-path control, add --paths positive.json current.json and observe alias_uniqueness=PASS.

## Evidence boundary

These are synthetic static examples, not live Notion/Obsidian content, real paid x402 transactions, proof of a successful workflow, authenticated source freshness, proof of custody, customer demand, external acceptance, or service accreditation. This package does not execute arbitrary path entries, contact others, require credentials or spend money. Review is required before merge; release gate [#98](https://github.com/aymanaseriai-cell/agent-economy-os-2047/issues/98) remains in force.

