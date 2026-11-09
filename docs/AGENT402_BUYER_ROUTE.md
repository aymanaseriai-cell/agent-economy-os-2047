# Agent402 Buyer Route — Agent Economy OS 2047

This page describes **two existing public x402 v2 services on Base**. Listing, eligibility, health, quoted prices and search ranking can change. No paid transactions or buyers are implied by being listed.

## Available paid routes

| Service | Direct paid GET resource | Price | Intended buyer |
| --- | --- | --- | --- |
| Base USDC Receipt Evidence Lite | `https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-usdc-receipt-lite/api/v1/receipt` | 0.005 USDC | Agents checking a Base USDC transaction hash through independent RPC endpoints |
| Base USDC Receipt Evidence | `https://jzallxzbbdtelcpabfgr.supabase.co/functions/v1/agent-usdc-receipt/api/v1/receipt` | 0.01 USDC | Agents reconciling Base-USDC transfers |

Both accept GET with required query parameter `tx`; optional parameters: `to`, `min_usdc`, and `min_confirmations`. The public paywall returns HTTP **402** with an x402 v2 `payment-required` challenge. Any actual purchase requires an independent, funded x402 buyer client; this project does not send or sign purchases on the reader's behalf.

**Buyer task discovery (FREE):**
- Search query: *Verify a native USDC transfer on Base using 2 of 3 independent RPC providers with transaction hash*.
- Agent402 `POST https://agent402.tools/api/route` with `{"query":"Verify a native USDC transfer on Base using 2 of 3 independent RPC providers with transaction hash"}` returns ranked candidate tools. This is discovery, not execution.
- The external Agent402 index lists our two low-cost tools under the **unproven seller tier**, with `executeViaCallableNow=true` and `executeViaLane="unproven"` as checked on 9 November 2026. Independent buyer requests may be routed to them when a task matches; neither route is guaranteed buyers or volume.
- `routerDispatchEligible=false` at the **origin** level is compatible with the **tool** being callable in the unproven tier. Consult tool-row fields, not just the origin summary.
- Direct seller-discovery endpoint for a route: `https://agent402.tools/api/index?seller=` followed by the URL-encoded full route origin.

## Buyer trust checks

Before paying, the buyer must verify the x402 quote independently:
- Network: `eip155:8453` (Base mainnet).
- Token: native USDC on Base, contract `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`.
- Payee: `0x935ad91b70c6d0769871416c5904d06fbf9ef586`.
- Correct expected micro-USDC amount: `5000` or `10000`.
- A credible real transaction hash and enough confirmations are required to establish actual settlement evidence. A payment quote or a demo does **not** prove the service is fit for a production use case.

## Monitoring (seller-side)

GitHub Actions workflow `agent402-seller-health.yml` performs a read-only health probe every six hours:
1. Fetches each public Agent402 seller-index snapshot.
2. Confirms current tool-level callability on the unproven tier.
3. Retrieves a normal unsigned x402 HTTP 402 quote and validates exact network, asset, payee and amount.
4. Performs one free task-route lookup and saves rankings in a short-lived GitHub Actions artifact.

The workflow never sends a wallet key, signs a payment, executes a routed paid call, purchases its own services or sends unsolicited outreach. Its reports **cannot be used as accounting statements or proof of revenue**.

Current market uncertainty: volume depends on independent buyer needs, competing sellers, eligibility changes, and public endpoint uptime.
