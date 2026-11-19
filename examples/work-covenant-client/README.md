# Work Covenant public self-serve demo

A **standard-library-only** Python client for the deployed Work Covenant API,
available without a login, wallet or payment. Its default mode is offline.

### Reproduce
```bash
python3 examples/work-covenant-client/client.py
python3 examples/work-covenant-client/client.py --live
```

The first command prints the public endpoint and makes **zero network requests**.
The second command fetches `GET /demo` from the Cloudflare gateway, then sends
**only the public sample response** back to `POST /v1/evaluate`. It checks the
returned contract ID, SHA-256-formatted proof ID, all technical check results and
explicit negative payment/buyer-acceptance assertions.

For a direct comparison of the primary service, run:
```bash
python3 examples/work-covenant-client/client.py --live --origin primary
```

Both origins are hardcoded to official read-only/stateless Work Covenant services.
Requests to arbitrary endpoints or user-supplied URLs are intentionally blocked.
The client refuses unexpected redirects and bounded response/request sizes.
It never uses private keys, API tokens, user files, payment accounts, escrow,
USDC transfers or real customer records. The CI runs **offline only**.

### What does a passing report mean?
It demonstrates that the **caller-supplied demo artifacts** satisfy caller-supplied
checks, and nothing more. It is **not** evidence of independent execution, legal
acceptance by a buyer, delivery, intellectual-property rights, payment, receipts,
settlement or real sales. A contract ID and proof ID are hashes, not signatures.
The API still needs a trusted buyer-side acceptance mechanism for commercial use.

This example does not modify Cloudflare or Supabase configuration and does not
represent an official A2A, MCP or x402 SDK.
