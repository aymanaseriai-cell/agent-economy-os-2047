# Agent Economy OS 2047

[![CI](https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/workflows/ci.yml/badge.svg)](https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/workflows/ci.yml)
[![License MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**A working open-source toolkit for evidence integrity in AI-agent workflows and automatic public GitHub readiness reviews.**

## ✅ Try the automated free audit

**[Open a free public repo audit request](https://github.com/aymanaseriai-cell/agent-economy-os-2047/issues/new?template=free-repo-audit.yml)**

When a public repository URL is submitted through the Issue Form, GitHub Actions automatically checks seven public signals (README, license, security policy, CI workflow, issue form, Dependabot configuration, and description) and posts the results back in the Issue. **It does not run the target repo's code and does not claim to assess its security.** GitHub Actions must be enabled for this to operate.

## ✅ Verify AI-agent evidence locally

No API keys or external dependencies. Python 3.10+.

```bash
python3 verifier.py evidence-manifest.json --root . --json-out evidence-report.json
python3 -m unittest discover -s tests -v
```

The SHA-256 file manifest looks like this:

```json
{"artifacts":[{"path":"examples/output.txt","sha256":"8ea1a19745343ce9f34808b3ad2448a8efb61402db51980b43147106bf66c41e"}]}
```

The exit code is 0 for all files matching the manifest; otherwise it is 1. **Matching a hash establishes consistency with a manifest, not independent proof of execution or trustworthy agent output.**

### Reusable GitHub Action

In another repository's GitHub Actions workflow, first check out the target repo and then call this action with a **reviewed commit SHA**:

```yaml
name: Verify evidence
on: [push, pull_request]
permissions:
  contents: read
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aymanaseriai-cell/agent-economy-os-2047@YOUR_REVIEWED_COMMIT_SHA
        with:
          manifest: evidence-manifest.json
          root: .
```


## 🔐 OKX guarded real-order executor

The six-agent + seven-quant-system scanner has a **separate authenticated execution adapter** capable of submitting *real* OKX USDT perpetual orders **when the repository's live-mode variables, credentials, arm secrets and workflow confirmation are enabled**. The code defaults to `dry_run`; connected repositories may be configured for real-money live trading. Scanning requires estimated 24-hour turnover ≥ **$15 million** (up to 12 instruments). Exchange-side controls include 10x isolated net-mode leverage, cooldown after a fully closed position, spread and turnover checks, duplicate-order checks, attached TP/SL and protective-order reconciliation. The default `guarded` sizing targets 0.25% equity-at-stop; an explicitly armed `full_margin` alternative risks substantial losses, including liquidation. **No daily realized-loss circuit breaker or proven profitable edge is implemented.** [Live setup and risks](trading/LIVE_TRADING.md) · [execution workflow](.github/workflows/okx-guarded-execution.yml).

**NVIDIA is now research-only and separate:** the [NVIDIA advisory workflow](.github/workflows/okx-nvidia-advisory.yml) analyzes fresh public quantified signals and publishes a read-only report of BUY/SELL/WAIT opinions and risk notes. It cannot authorize, block, size, or submit OKX orders; failures never alter the trading executor. An eligible quantitative signal is still required.

## 🧠 Six-Agent OKX Futures Council
**QUANT2037 update:** Six market-specialist agents are now cross-checked by seven additional numerical systems for jump risk, entropy, variance ratio, approximate profile migration, L2 depth fragility, aggressor-flow acceleration and counterfactual vote stability. The second stage may only **veto**, never force an entry. [Read the design and limitations](trading/QUANT2037.md). Analysis only, with no credentials or actual trading.
 (research-only)

[Run the six-agent public-market scanner](https://github.com/aymanaseriai-cell/agent-economy-os-2047/actions/workflows/okx-six-agent-council.yml). Six auditable specialist analysis roles read OKX orderbook, recent trades, funding, open interest, completed 15m/1h/4h candles and an **approximate** 48-hour volume profile. Runs on a GitHub Actions schedule (which can be delayed) and uploads a JSON evidence report. **No credentials, trading permissions, buy/sell orders, funded account, claimed win rates or guaranteed returns.** [Technical details](trading/SIX_AGENTS.md).

## 🤖 Other actual automations

- **Inbound free audit → analysis → reply:** `.github/workflows/issue-router.yml` + `automation/issue_router.py`.
- **Daily public opportunity radar:** `.github/workflows/opportunity-radar.yml` generates an artifact containing public issue candidates. It never sends unsolicited messages.
- **Continuous / daily tests:** `.github/workflows/ci.yml`; verified sample output can be downloaded as a workflow artifact.

Run a public repo readiness audit yourself:

```bash
python3 automation/repo_audit.py aymanaseriai-cell/agent-economy-os-2047 --json-out report.json
```

Automation runs on GitHub's infrastructure, subject to GitHub Actions service availability, permissions and API rate limits. Scheduled workflows may be delayed by GitHub.

## 💵 Commercial paths (status is important)

| Path | Status | Honest limitation |
| --- | --- | --- |
| GitHub Sponsors | **Registration required** | No sponsor payout is set up by this code. Sponsorship requires GitHub approval and payout onboarding. |
| Custom GitHub/AI-agent workflow integration | **Public request form ready** | [Request a quote](https://github.com/aymanaseriai-cell/agent-economy-os-2047/issues/new?template=service-request.yml). Starting indicative quote: **$49 USD** for a small public-repository scope, subject to agreement. No automatic payments. |
| Future hosted SaaS / subscriptions | **Not launched** | Requires a deployed service, customer authentication and functioning payment provider. |

Nothing in this repository guarantees paying customers, automatic cash transfers, or a specific income. Public Issues are not an order, payment authorization, or SLA.

## 🔐 Safety and community

Do not publish private client information, tokens, passwords or bank details in issues. Read [SECURITY.md](SECURITY.md) and [CONTRIBUTING.md](CONTRIBUTING.md). MIT licensed.
