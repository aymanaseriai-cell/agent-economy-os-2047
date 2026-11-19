# Quickstart: verify one synthetic agent deliverable

Use **Node.js 24** from the repository root. No package installation, wallet, API keys, customer data, external URLs or funded test accounts are required.

```sh
node examples/proof-carrying-work/run.mjs
```

The offline script:
1. Defines caller-supplied acceptance criteria for `report.json`.
2. Computes a SHA-256 digest and stable `contract_id`.
3. Evaluates the intended JSON bytes and returns `local_checks_passed`.
4. Alters the content and returns `local_checks_failed`, showing a hash mismatch.
5. Leaves `buyer_acceptance_verified` and `payment_verified` set to `false`.

Run the automated negative and positive tests:

```sh
node --test tests/work_covenant/*.mjs
python3 -m unittest discover -s tests -v
```

No local result proves independently who executed the task, whether the acceptance criteria came from an authorized buyer, the work's commercial value, delivery, or any payment. For the public test API and optional Ed25519 endorsement, see [Work Covenant](WORK_COVENANT_2047.md). Never submit secrets to the public demo.
