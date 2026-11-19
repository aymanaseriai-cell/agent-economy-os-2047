# Zero-trust Agent Action Policy — offline preflight

Original, dependency-free security preflight for Agent Economy OS 2047, informed
by the architecture and MIT-licensed policy validation patterns of
https://github.com/microsoft/agent-governance-toolkit . No competitor code was
copied into this feature.

## Security boundary

This tool **does not authenticate an agent or enforce actions**. The principal
is a caller-supplied string. A successful evaluation means only that local
structured values match an operator-supplied policy. The tool performs **no**
network calls, repository changes, trading, settlement, payment, account or
database writes. The policy digest is not a cryptographic signature.

- Deny by default; no wildcards; exact principals, resources and environments.
- Explicit denies override allows. Expired rules are not matched.
- Only a closed set of harmless inspection/evaluation actions is allowlisted.
- Stateful or financial actions are always denied, including transfers, x402,
  DB writes, deployment, trading, secrets and messages.
- Strict JSON parsing rejects duplicate keys, nonfinite numbers and large files.
- Reports preserve policy hash, deny reason, and explicitly label unverified
  caller identity and absence of real execution.

## Run

Create `request.json`:
```json
{"schema":"agent-economy.action-request.v1","principal":"audit-agent",
 "action":"evidence.inspect","resource":"service:work-covenant",
 "environment":"staging"}
```

```bash
python automation/agent_action_policy.py policies/agent_action_policy.example.json request.json
python -m unittest discover -s tests -p 'test_agent_action_policy.py' -v
```

The provided policy and fictional principal are **examples**, not live
credentials or a production grant.

## Before integration into any actual agent runtime

1. Authenticate principals via a trusted identity provider and never trust
   a user-provided principal field as proof of identity.
2. Bind policy to a reviewed, protected revision; use code review and an
   independently validated release signature if needed.
3. Enforce decisions server-side before execution; record immutable audit
   evidence and evaluate race/replay threats.
4. Build idempotency and reconciliation separately for any real write actions.
5. Review applicable legal/security requirements before any x402/payments.

This component is intentionally review-only: there is no live production
integration, no new financial flow and no claim of full feature parity with
Microsoft's governance toolkit.
