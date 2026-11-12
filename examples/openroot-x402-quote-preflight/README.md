# x402 quote guard — offline buyer preflight

A zero-dependency Python 3.10+ **read-only** sample for autonomous agents to evaluate a captured **x402 v2** `PAYMENT-REQUIRED` header before asking the wallet owner to approve a payment.

This is an open-source learning example for builder communities, including potential OpenRoot developer collaborators. **It does not integrate with OpenRoot infrastructure, send payments, prove transactions, assess merchant legitimacy, or guarantee refunds or delivery.**

## Reproducible local use

Capture a protected x402-v2 route's `PAYMENT-REQUIRED` response header **without any payment signature**. Put the Base64 header value, or its decoded JSON, into `challenge.txt`. Pin buyer policy values **independently of the remote response**:

```sh
python3 examples/x402_quote_guard.py challenge.txt \
  --expected-url 'https://merchant.example/api/receipt' \
  --expected-payee '0x935ad91b70c6d0769871416c5904d06fbf9ef586' \
  --max-atomic 10000
```

The example payee and URL above must be replaced with the actual preapproved merchant policy. `10000` micro-USDC equals `0.01 USDC`. A consistent challenge returns exit status `0` and `eligible:true`; a mismatch returns `2` and explicit error codes. **Neither result authorizes a payment**; wallet-owner approval, merchant trust, delivery verification and on-chain settlement remain separate steps.

This intentionally accepts only one unambiguous `exact` payment option, x402 version 2, Base `eip155:8453`, the official Base USDC address, exact resource URL, independently pinned recipient and bounded amount/time. It fails closed otherwise. It never makes HTTP calls, signs transactions, reads keys or receives passwords.

## Run tests

```sh
python3 -m unittest discover -s tests -p 'test_x402_quote_guard.py' -v
```

**No wallet, signup, capital, or sensitive inputs are needed.** Use synthetic test fixtures; never commit real transaction identities or buyer payment credentials to a public repository. This does not replace an audited wallet spending policy.
