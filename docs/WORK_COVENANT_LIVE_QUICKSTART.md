# Five-minute public Work Covenant integration

Use Python 3.10+ with no additional packages, API keys, wallet, account or private data.
From a fresh checkout of the repository, run:

    python3 examples/work_covenant_live_quickstart.py
    python3 -m unittest discover -s tests -p 'test_work_covenant_live_quickstart.py' -v

The script makes GET /demo and two POST /v1/evaluate requests to the deployed
public beta endpoint. A correct synthetic report must pass; a tampered report
with ok=false must fail criterion status_ok. The script rejects any response
claiming buyer approval, payment or on-chain settlement as verified.

The unit tests run offline with fake HTTP responses. The script itself makes
real network calls and can fail if the public beta is unavailable or changes.

Neither result proves external adoption, provenance, legal delivery,
buyer authorization, independently verified work, or revenue.
Only public synthetic example data is sent.

Endpoint: https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-work-covenant-2047
Optional scope inquiry: https://github.com/aymanaseriai-cell/agent-economy-os-2047/issues/new?template=service-request.yml
