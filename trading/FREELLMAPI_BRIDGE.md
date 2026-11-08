# TITAN QUANT2037 x FreeLLMAPI unified research gateway

Upstream: https://github.com/tashfeenahmed/freellmapi
Installation: https://github.com/tashfeenahmed/freellmapi/blob/main/docs/en/install/01-install.md
API docs: https://github.com/tashfeenahmed/freellmapi/blob/main/docs/en/api/01-rest-api.md

## Implemented

trading/freellmapi_bridge.py provides an optional self-hosted FreeLLMAPI
OpenAI-compatible client, with auto:smart, auto:fast, auto:reliable,
auto:balanced, auto:cheap, auto and fusion model options.

Only fresh, eligible public six-specialist + seven-quant scan hypotheses
can be reviewed, using the existing NVIDIA public_snapshot gate.
Research outputs are advisory only; WAIT always remains WAIT.
No connection to the real trade execution code is added.

20 offline tests exercise URL/key isolation, manual inference opt-in,
strict JSON, prompt injection resistance, stale evidence, uncertainty,
never leaking secrets into output, no redirect, and no order authority.

## Important distinction about FreeLLMAPI keys

FreeLLMAPI aggregates free service TIERS. It does not supply legitimate
secret keys to every upstream provider. You register your own provider
accounts and put keys in your PRIVATE FreeLLMAPI dashboard.

The project's existing NVIDIA_API_KEY GitHub secret CANNOT be read or
copied out of GitHub. It is not the distinct unified FreeLLMAPI gateway
key. We have not manufactured or installed a fake key, nor accessed
any provider with a production request during this task.

## Private local Windows setup

1. Install upstream FreeLLMAPI Windows desktop release from
   https://github.com/tashfeenahmed/freellmapi/releases/latest
   or follow upstream Docker instructions.
2. Open the local dashboard at http://localhost:3001. Add the provider
   credentials from YOUR accounts to the Keys page (NVIDIA if permitted,
   plus other provider accounts at your discretion) and configure
   fallback priorities.
3. Copy the distinct unified FreeLLMAPI API key from the local Keys page.
   NEVER paste it into the GitHub repo, screenshots, or chat.
4. Set local process environment securely (not as literals committed
   to source):
   FREELLMAPI_BASE_URL=http://127.0.0.1:3001/v1
   FREELLMAPI_API_KEY=<your generated unified router key>
   FREELLMAPI_MODEL=auto:smart
   FREELLMAPI_ENABLE_REQUESTS=YES
5. Check with: python -m trading.freellmapi_bridge --mode status
   This command sends NO API requests.
6. Generate a new public research scan with:
   python -m trading.six_agent_council --top 6 --out reports/new_public_scan.json
7. Request one opt-in research review:
   python -m trading.freellmapi_bridge --mode evaluate --report reports/new_public_scan.json --out reports/free_router_review.json

If the scan has no eligible direction or is older than 150s, no inference
request is made. One outgoing FreeLLMAPI call at most per review;
the gateway may itself do internal routing/fan-out, especially fusion.
Fusion is NOT independently verified agreement across models; do not
use it as a replacement for the separate NVIDIA execution gate.
Its provider-level free quotas cannot be guaranteed by this adapter.

GitHub Actions localhost is NOT your Windows localhost. The test
workflow runs OFFLINE with NO secrets, paid inference, or exchange orders.
If later using a private remote HTTPS router that you own, configure
a fully qualified HTTPS URL with explicit port and exact allowlisted
hostname FREELLMAPI_ALLOWED_HTTPS_HOST. Do not expose a single-user
FreeLLMAPI dashboard to the public Internet.

## Safety

Keys only in environment or secure local dashboard. No API credentials
hardcoded or exported. Inference OFF until manual explicit opt-in. The
gateway response NEVER places orders or authorizes the OKX executor.
It does not validate profit, and numerical AI confidence is uncalibrated.
The original trading workflow stays DISABLED, real trading NO/dry_run.

Public FreeLLMAPI free-tier policies and availability change, and
upstream warns against relying on free tiers in production.
