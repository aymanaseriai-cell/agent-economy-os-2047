# Vendor integrity for pinned A2A assets

The files under `third_party/a2a/` are verbatim Apache-2.0-licensed
upstream sources, pinned by exact GitHub commit. `VENDOR_LOCK.json` stores
their SHA-256 values, source path, commit and SPDX license.

Run: `python automation/verify_vendor_lock.py`

CI checks that the four local files match their reviewed lock hashes and
blocks silent edits to the vendored protocol and sample data. This uses only
Python's standard library; no network calls or credentials.

**Trust limitations:** An attacker able to edit both the vendored files
and the lockfile can bypass byte-matching checks, so protected branches,
reviewers, signed provenance and trusted upstream verification are still
required. SHA-256 integrity is not provenance authentication.

Official sources:
- https://github.com/a2aproject/A2A/tree/5f931b8a25fe66789f987ec4a55fc16ee9fe41ee
- https://github.com/a2aproject/a2a-samples/tree/1d7b7be24971c60fe5019182c1d26b7e9ae137ed
