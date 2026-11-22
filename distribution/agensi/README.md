# Portable Buyer Acceptance Skill — review-only marketplace package

**Status:** Independent, source-pinned distribution candidate. This branch and its ZIP artifact are not a live marketplace listing, signed buyer acceptance, paid order or company production release.

This addresses one actual agent-buyer problem: acceptance criteria that live outside the delivering agent's control.

## Package and test

```bash
python3 -m unittest discover -s tests -p 'test_marketplace_skill_package.py' -v
python3 distribution/agensi/build_skill.py --out dist/agent-economy-buyer-acceptance-0.1.0.zip
```

The reproducible archive puts `SKILL.md` at archive root, with the existing standalone Python buyer-gate script and synthetic example artifacts. The builder copies `buyer-gate/check.py` byte-for-byte from the repository: it does **not** fetch or execute network code. All files are allowlisted. Archive timestamps and permissions are fixed, and a SHA-256 is emitted for independent comparison.

The package includes the repo's MIT license, exact supported technical checks and prominent limits. Its smoke-test policy hash is **NOT** evidence of an independent third-party policy pin.

## Marketplace readiness

Agensi's creator documentation describes a ZIP with a root `SKILL.md`, automated security screening and manual review. Its current terms state 70% creator revenue share and possible Solana USDC payout, but an actual listing requires an account, verified authorized payout mechanism and independent country/legal review. No signup, wallet signing, private key or seller authorization is included in this PR. Do not claim confirmed demand, listing, sales, or the platform's reported traffic as measured outcomes.

## Safety gate

No deployment of GitHub PRs #84 or #114, no change to issue #98, no customer contact, trading, wallet, payment, or production release. A seller may review the archive and independently submit only after satisfying the marketplace terms and local legal requirements.
