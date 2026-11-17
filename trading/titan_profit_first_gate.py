"""Fail-closed independent forward-PnL proof for new TITAN live entries.

No evidence has passed the check yet. Only a later, reviewed code change can
pin a trusted digest, after source fills and costs are independently audited.
Neither an env variable nor a public model prediction may approve evidence.
"""
import hashlib
import json
import math
import re
from datetime import datetime,timezone,timedelta
from pathlib import Path

AUDITED_PROOF_PATH=Path("reports/titan_forward_fill_proof.json")
REVIEWED_PROOF_SHA256=""  # Intentionally disarmed: zero qualified future fill reports.
KIND="TITAN_INDEPENDENT_PROSPECTIVE_EXECUTION_PROOF_V1"

def _finite_number(x):
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x):
        raise ValueError("Invalid audit numeric value")
    return float(x)

def _instant(x):
    if not isinstance(x,str):raise ValueError("Missing timestamp")
    v=datetime.fromisoformat(x.replace("Z","+00:00"))
    if v.tzinfo is None:raise ValueError("Timezone required")
    return v.astimezone(timezone.utc)

def validate_proof(blob, trusted_digest, *, now=None):
    """SHA pins reviewed evidence; a hash alone is not an audit of source fills."""
    if not isinstance(blob,bytes) or not blob or len(blob)>1_000_000:
        raise ValueError("No supported proof blob")
    if (not isinstance(trusted_digest,str) or
            re.fullmatch("[0-9a-f]{64}",trusted_digest) is None or
            hashlib.sha256(blob).hexdigest()!=trusted_digest):
        raise ValueError("No matching independently reviewed digest")
    p=json.loads(blob)
    if not isinstance(p,dict) or p.get("mode")!=KIND:
        raise ValueError("Historical/simulated proof is not accepted")
    flags=("untouched_forward_samples","independently_reconciled_fill_receipts",
           "realized_fees_and_funding_reconciled","tiny_equity_exchange_lots_verified",
           "liquidation_sensitivity_verified","stress_slippage_and_fees_verified")
    if any(p.get(k) is not True for k in flags):
        raise ValueError("Execution and cost provenance not reviewed")
    n=_finite_number(p.get("number_of_future_fills"))
    d=_finite_number(p.get("distinct_trading_days"))
    normal=_finite_number(p.get("net_return_after_costs_pct"))
    stress=_finite_number(p.get("stress_net_return_after_costs_pct"))
    lo=_finite_number(p.get("daily_net_95pct_lower_bound_usdt"))
    dd=_finite_number(p.get("max_drawdown_pct"))
    if n<200 or d<30 or normal<=0 or stress<=0 or lo<=0 or not 0<=dd<=15:
        raise ValueError("No positive, sufficiently sampled forward edge")
    start,end,generated=(_instant(p[k]) for k in
                         ("start_utc","end_utc","generated_utc"))
    clock=now or datetime.now(timezone.utc)
    if clock.tzinfo is None:raise ValueError("Naive time")
    if not (start<end<=generated<=clock and end-start>=timedelta(days=30)
            and clock-generated<=timedelta(days=90)):
        raise ValueError("Stale or too-short prospective proof")
    return True

def permitted_new_live_entry(*, path=AUDITED_PROOF_PATH,
                             trusted_digest=REVIEWED_PROOF_SHA256,now=None):
    if not trusted_digest:return False
    try:
        p=Path(path)
        if not p.is_file() or p.stat().st_size>1_000_000:return False
        return validate_proof(p.read_bytes(),trusted_digest,now=now)
    except (OSError,TypeError,ValueError,KeyError,OverflowError):
        return False
