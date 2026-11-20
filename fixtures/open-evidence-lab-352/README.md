# Open Evidence Lab — synthetic positive/negative artifact-integrity fixture

Reference: [probityai/agent-evidence-vectors issue #352](https://github.com/probityai/agent-evidence-vectors/issues/352).

**Claim tested:** a local, byte-for-byte SHA-256 manifest detects changed AI-agent output files **relative to a previously supplied reference digest**. This fixture does not assert that a completed task really ran, that any independent witness was present, or that the answer was correct.

## Fixture files and expected results

| Case | Input file | Manifest file | Expected result | Reason |
| --- | --- | --- | --- | --- |
| Positive | `positive.json` | `positive-manifest.json` | `passed=true`, exit `0` | File bytes match the declared SHA-256 digest |
| Negative | `negative.json` | `negative-manifest.json` | `passed=false`, exit `1`; error contains `sha256 mismatch: negative.json` | The `artifact` field changes from `answer: 42` to `answer: 43` without changing the trusted reference digest |
| Duplicate canonical path (regression) | `positive.json` referenced twice as `positive.json` and `./positive.json` | `duplicate-canonical-path-manifest.json` | `passed=false`, exit `1`; error contains `duplicate canonical artifact path: ./positive.json`; `checked=1` | Both valid, matching entries resolve to the same canonical file and must not be counted twice |

All values, task IDs and outputs are **synthetic**. No real agent task, payment or customer event is represented.

The two JSON input files are exactly one UTF-8 JSON line each, **including a final LF (0x0A)**. The reference SHA-256 of the complete bytes of `positive.json` is:

`d8ccfd1d2056c5f4625b8f6e26d2eed3baf89a1e63208bec893541d043fec15c`

Content canonicalization rule: **no JSON normalization**. SHA-256 applies to exact raw bytes as checked into Git. **Artifact paths are canonicalized separately** using `Path.resolve()`, which eliminates `.`/`..` components and resolves symbolic links, then confined to the chosen `--root`. Any two manifest entries resolving to the same canonical artifact path trigger a fail-closed error, even if both hashes match. This is a path uniqueness check, not a claim that the JSON content was canonicalized. The manifest's `artifacts` array contains `path` and lowercase 64-character hexadecimal `sha256`. Both manifests deliberately declare the **same original digest**. `schema_version` is a fixture documentation tag, not a validator-enforced field.

## Exact independent reproduction

With Python 3.10+ and Git (no dependencies, network credentials, secrets or API keys):

```bash
git clone https://github.com/aymanaseriai-cell/agent-economy-os-2047.git
cd agent-economy-os-2047

python3 verifier.py fixtures/open-evidence-lab-352/positive-manifest.json --root fixtures/open-evidence-lab-352
# Expected exit code: 0; passed: true; checked: 1; errors: []

python3 verifier.py fixtures/open-evidence-lab-352/negative-manifest.json --root fixtures/open-evidence-lab-352
# Expected exit code: 1; passed: false; errors contains "sha256 mismatch: negative.json"
```

### Duplicate-canonical-path reproduction (requested regression)

```bash
python3 verifier.py fixtures/open-evidence-lab-352/duplicate-canonical-path-manifest.json --root fixtures/open-evidence-lab-352
# Expected exit: 1; passed: false; checked: 1
# Error: artifacts[1]: duplicate canonical artifact path: ./positive.json (same as artifacts[0]: positive.json)
```

This manifest deliberately declares **two valid, matching SHA-256 entries** whose paths are lexical aliases. The original single-entry byte-integrity check is not sufficient to detect this issue. The fail-closed path-uniqueness check is also covered by unit tests for identical entries, `./` aliases, and symlink aliases, with a distinct-files positive control. On platforms without symlink creation support the symlink unit test is skipped. **Hardlinks, concurrent filesystem mutation and signed provenance are outside the claim.**

A non-author can also inspect the raw files and compute SHA-256 independently using Python's standard `hashlib`, then compare the calculated hash with the manifests. **Do not alter line endings** when reusing the exact digests. Use a reviewed commit permalink when running in a higher-assurance environment.

## Independent pre-publication dry run

Tested locally against this repository's `verifier.py` source on 2026-11-20:
- Positive: exit 0, `passed=true`, `errors=[]`.
- Negative: exit 1, `passed=false`, error `artifacts[0]: sha256 mismatch: negative.json`.

**Limitations:** A malicious producer can replace both the output and the manifest. Passing hash integrity is not evidence of real execution, honest generation, authorship, externally trusted time, safety, signed attestation, payment, or independent acceptance. These cases remain candidates for external review, **not** an accepted Lab fixture or change to ProbityAI's frozen PriorSeal matrix.
