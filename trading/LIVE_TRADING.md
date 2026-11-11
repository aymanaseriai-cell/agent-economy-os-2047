# OKX 6 agents + 7 systems — guarded real execution adapter

**FULL-MARGIN OPTION:** A separately armed `full_margin` mode can target **up to 100% of available USDT isolated margin**, with 20x leverage. This bypasses the guarded mode's 0.25% per-stop sizing and 20% notional cap. Full-margin trading can liquidate the account and is NOT a proven profitable strategy. It refuses trades with an estimated initial-stop risk greater than 10% of equity; actual losses can be larger due to gaps, fees, liquidations and execution failure. It does not automatically enable trading.\n\n**Real trading execution is implemented in `trading/okx_live_executor.py` but DISARMED until you explicitly configure it. No guarantee of profit.**

## Live-capable architecture

- Public-data 6-agent / QUANT2037 signal engine scans **up to 12** USDT perpetual instruments, with estimated 24h base-coin turnover **≥ US$15 million**. This is turnover, **not order-book liquidity**, and is not a guarantee of executable depth.
- Fresh `LONG` or `SHORT` must pass the six-agent scoring, seven independent quantitative veto filters and all exchange-side checks. No forced trades. Stale report, ambiguous signal, data errors or mismatched account mode result in **no trade**. NVIDIA recommendations are never an execution gate.
- Separate private execution engine authenticates using OKX REST API v5, checks account `net_mode`, positive free USDT equity, no outstanding perpetual position or order, 24h bot order count, current contract specification, spread, instrument turnover and current price.
- **Default guarded sizing** caps intended risk at **0.25% equity per order**, **20% equity gross notional**, **5% initial margin**, **20x leverage**. These are planned entry sizes in guarded mode, **not maximum realized loss**: gaps, slippage, funding and liquidation can cause larger loss.
- Only USDT-margined **linear isolated** perpetuals with `ctValCcy` equal to base asset are supported. Position quantity is quantized down to `lotSz`, never rounded up to `minSz`.
- Sets isolated leverage to 20x after preflight, then sends a single market order with **exchange-native attached stop-loss and take-profit**. Verifies fills and attempts verification of attached protective orders; unprotected fills trigger an emergency reduce-only market close attempt. **Neither stop orders nor emergency close are guaranteed to execute during outages.**
- **At least 10 minutes between any fully closed SWAP position and the earliest possible subsequent entry**, measured using the OKX server's authenticated `GET /api/v5/account/positions-history` `uTime`. A liquidation or fully closed ADL event also starts the cooldown. The bot checks this twice per entry and refuses trades if exit history is unavailable or ambiguous. This is a minimum wait, not a promise of a new signal/order at exactly 10 minutes.\n- **No fixed numerical maximum of bot orders per day.** This does **not** mean continuous trading: a fresh vetted 6-agent+7-system signal, no existing position/pending order, correct exchange-side protective orders and the **10-minute re-entry cooldown** are still mandatory. A full 24-hour order-history scan remains required to detect replayed client IDs. This is a high-loss-risk configuration, especially with full-margin allocation. An automated daily realized-loss limit is **not** implemented, so live activation is unsuitable without separate persistent drawdown protection.
- No key or balance logging, no withdrawals, transfers, or balance sweeping. Execution never calls NVIDIA; a **separate optional** NVIDIA advisory workflow sends only public market evidence to the NVIDIA inference API, and never receives account credentials or position details.

## Enter OKX credentials **securely** (public repository)

1. Revoke every old OKX API key ever posted in chat or code. In OKX create a **new** `Read` + `Trade` key (never `Withdraw`). Ideally use a dedicated sub-account and enforce a source IP allowlist on a stable-IP server.
2. In the repository's **Settings → Secrets and variables → Actions → Repository secrets**, create:
   - `OKX_API_KEY` = your new API key;
   - `OKX_SECRET_KEY` = your new API secret;
   - `OKX_PASSPHRASE` = your new OKX API passphrase.
   **Do not put these in source code, issues, commit messages, chat, Actions variables or shell commands.**
3. Under **Settings → Secrets and variables → Actions → Repository variables** set `OKX_EXECUTION_MODE=dry_run` initially, and if needed `OKX_API_DOMAIN=https://www.okx.com` (or region-appropriate `https://eea.okx.com` / `https://us.okx.com`).
4. Open **Actions → OKX guarded execution → Run workflow**, choose `validate`. This performs an authenticated **read-only** request, prints whether the account is in `net_mode`, and **never places an order**.
5. To test demo, use **OKX demo credentials** and set variable `OKX_EXECUTION_MODE=demo` plus secret `OKX_EXECUTION_ARM=CONFIRM_DEMO_ORDER`.
6. Optional **full available margin** sizing (particularly hazardous): configure repository variable `OKX_CAPITAL_MODE=full_margin` AND repository secret `OKX_FULL_MARGIN_ARM=I_ACCEPT_FULL_MARGIN_LIQUIDATION_RISK`. Until **both** are configured, full-margin trading is BLOCKED; the default remains `guarded`. A 10% estimated equity-at-stop cap may reject the trade instead of reducing its size. The exchange's `max-size` quote, lot rounding and fees may prevent exact 100% utilization; **never promise all available equity will be deployed**.\n7. **Real-money arming is a separate opt-in:** only after evaluating the demo and independently verifying account setup, set variable `OKX_EXECUTION_MODE=live`, set variable `OKX_ENABLE_REAL_TRADING=YES`, and set secret `OKX_EXECUTION_ARM=I_ACCEPT_REAL_MONEY_LOSS`. At that point scheduled runs *can submit real orders* without another prompt when a valid signal exists. Set either variable back to `dry_run` or `NO` immediately to stop new entries.

**Do not enable live mode with a key you have already disclosed elsewhere.** The workflow deliberately defaults to `dry_run` even when a valid trading key exists. The workflow does not switch account mode: OKX must already be `net_mode` and able to use USDT isolated perpetual margin.

## Scan cadence and the 10-minute re-entry rule\n\nGitHub Actions requests scans **every five minutes**; the previous schedule was every fifteen minutes. If a position is fully closed at 12:03, the next eligible run could be 12:17 or later depending on scheduling and signals. No trade is forced. There is no fixed bot order-count cap, although the scanner may return WAIT and the ten-minute post-exit wait still applies. The six-agent and seven-quant-system confirmations, position exclusivity and capital-mode opt-ins remain mandatory.\n\n## GitHub-hosted runner risks\n
GitHub Actions schedules **may delay or skip runs**, executions are ephemeral and cannot continuously monitor positions, and hosted runner IPs are not stable for reliable OKX API IP allowlisting. The system relies on exchange-native TP/SL after entry, **but GitHub Actions is not a safe substitute for a 24/7 execution/risk daemon**. An always-on private server with static IP, durable state, persistent PnL/drawdown limit, real-time health checks and kill switch is strongly preferred for production live trading.

There is **no backtested or live-verified positive expected return**. The six agents are deterministic analysis components, not six autonomous LLM instances. Seven advanced numerical systems are veto filters; "2037" is branding, not a claim to quantum computation.

## Emergency stop

Switch repository variable `OKX_ENABLE_REAL_TRADING` to `NO` and/or `OKX_EXECUTION_MODE` to `dry_run`, **then inspect existing positions and protective orders directly in OKX**. Disarming prevents new bot entries but does not close existing positions or stop working exchange-native protection orders. Revoke the API key if needed.

## More safety gates needed before treating this as production-grade

Current v1 does **not** have a fully independently reconciled realized-PnL daily drawdown monitor, transaction-proof persistence across crashes, guaranteed protection-order reconciliation across all OKX account modes, stable-IP secret allowlisting, or historical profitable performance. It deliberately caps bot order count and size and fails closed on unfamiliar conditions, but this does not cap all possible monetary losses. Test with isolated demo credentials before using live.

API references: https://www.okx.com/docs-v5/en/ | https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions


## Opt-in chained GitHub sessions (20-second handoff)

The `okx-guarded-execution.yml` workflow supports an **optional** chained session mode. In **Actions → OKX guarded execution → Run workflow**, choose `purpose=run`, check `confirm_live`, `continuous` and `confirm_continuous_live`. The new controls are off by default, so a previous **one-off** manual confirmation cannot silently become unlimited live trading. Set `OKX_EXECUTION_MODE=dry_run` first to validate the mechanism without placing orders. Real trading requires the separate account and secret arm checks described above.

Each worker session has a **245-second** bounded runtime. Only when the worker exits **successfully due to the normal time limit**, the workflow sleeps **20 seconds** and requests a fresh `workflow_dispatch` using the repository-scoped `GITHUB_TOKEN`. A repository-level concurrency group prevents overlapping execution jobs. GitHub queue time, runner startup, and service availability mean **20 seconds is the delay before requesting the next run, not a guaranteed time to execution**. GitHub Actions is not an always-on host and the chain can be interrupted.

**Fail-closed:** No automatic re-dispatch on market scanner / NVIDIA / executor errors, ambiguous order state, a placed order, protective-order concerns, or an early risk-veto stop. These cases need manual investigation rather than blind retries. A valid trade signal and 10-minute exchange-side re-entry cooldown are still required. The 20-second job handoff is **not** a 20-second trading cooldown.

**Stop:** In `Settings → Secrets and variables → Actions → Variables`, set `OKX_STOP_CONTINUOUS=YES` to prevent a clean worker from scheduling its next run. Also set `OKX_ENABLE_REAL_TRADING=NO` or `OKX_EXECUTION_MODE=dry_run` to block all new live orders; then review any open OKX positions and exchange-native TP/SL manually. To resume the chain, remove the stop flag or set it to `NO` and manually initiate a new, explicitly confirmed workflow run.

Continuous hosted sessions can exhaust usage quotas and accumulate losses. Production trading requires an always-on risk service, circuit breakers, reconciliation, stable IP and monitored loss limits; none is supplied by GitHub Actions chaining.

## NVIDIA research only — detached from real trade decisions

The live executor (`trading/okx_live_executor.py`) does **not** import or invoke NVIDIA and does **not** use model advice to approve/reject entries. A separate [read-only NVIDIA advisory workflow](../.github/workflows/okx-nvidia-advisory.yml) performs its own public-market scan (12 instruments maximum), selects a fresh qualifying quant signal, and optionally asks NVIDIA's six research roles to report a directional opinion and uncertainty/risk notes. The resulting JSON artifact contains public research only — not account details, balances, API keys or order information. It reports `NO_SIGNAL` if the quant scanner finds no eligible trade.

Advisory output can be `BUY`, `SELL`, `WAIT` or `UNAVAILABLE`, but it is **never passed to the OKX executor**. An AI timeout, missing key, opposing opinion or partial response does not suppress a quant-approved candidate. Neither NVIDIA nor the quant system guarantees profitability; independent checks on position state, cooldown, exchange availability, leverage, size, stop/target validity, freshness and protection remain mandatory.

This intentionally removes an advisory risk-veto layer. **It increases potential trading exposure, especially when live mode and `full_margin` are armed.** Users should prefer `dry_run`/demo, rotate any previously disclosed keys and install persistent realized-loss cutoffs before real-money automation.

## Explicitly armed return-to-market after a verified exit

The default live executor stops after an order. To keep polling **after** a verified `FILLED_PROTECTED` entry and consider another independent candidate, the manual execution workflow now offers *two additional opt-ins* (`resume_after_exit` + `confirm_repeat_entries`), in addition to `purpose=run`, `confirm_live`, `continuous`, and `confirm_continuous_live`. The new options default to **false**; existing runs do not silently become repeat-order authorization. GitHub Actions session handoff is requested 20 seconds after clean bounded work, but queue time and uptime are not guaranteed.

In this mode the worker queries **only authenticated GET endpoints** before each scan. If one USDT-SWAP position is still open with attached TP/SL verified, it watches without new entries. If the position is closed, it verifies authenticated OKX `positions-history`; **no entry is eligible for at least 10 minutes after the last full position exit**. After that it still needs a **new** eligible 6-agent + 7-system signal, exchange account preflight, available margin, no pending/algorithmic orders, and fresh data. Unknown position, pending orders, lost protection, missing history, network error or uncertain order result **halts** the chain; never blindly retries a trade.

**Recurring entry configuration:** There is now **no fixed limit of two entries per day**. When `OKX_CAPITAL_MODE=full_margin` and `OKX_FULL_MARGIN_ARM=I_ACCEPT_FULL_MARGIN_LIQUIDATION_RISK` are separately configured, auto re-entry is allowed to plan **up to 100% of currently available isolated USDT margin per fresh trade** with 20x leverage. Exact usage is constrained by OKX max-size, contract rounding, fees and the existing rejection if planned initial-stop risk exceeds 10% of equity. It never stacks entries during an open position, never re-enters before the exchange-verified 10-minute full-exit cooldown, and never bypasses exchange checks, TP/SL verification, signal vetoes, duplicate order protection or shutdown on uncertain status. **Full-margin repeated trading can rapidly liquidate the account**; there is **no persistent realized daily-loss kill switch**. Unlimited permission does not mean guaranteed entries or continuous uptime. Never reuse exposed keys. For stopping: set GitHub variable `OKX_STOP_CONTINUOUS=YES`, `OKX_ENABLE_REAL_TRADING=NO` and check open positions and stops directly in OKX.

This feature does NOT force a trade; it permits the next approved trade only if all independent conditions pass, and cannot run permanently if GitHub queues or runners stop.

## 2026-11-08: Exchange cooldown history races (fixed in code)

OKX can mark a SWAP position flat before the full close appears in its
`positions-history` feed. A monitor may briefly return `FLAT_ELIGIBLE`
while the subsequent executor sees the new closure and the full ten-minute
cooldown. For **separately armed recurring sessions only**, this specific
verified cooldown is reported as `REENTRY_COOLDOWN_NO_ORDER` (successful
no-order outcome). The worker sleeps 30 seconds and rechecks the authenticated
read-only OKX monitor. The session chain continues across normal bounded
GitHub Actions handoffs. **The executor never bypasses or shortens the
cooldown; both pre-order cooldown validations remain in place.**

Any other exchange block, ambiguous or stale history, failed protection, missing
position information, model/signal error or uncertain POST status still stops
the worker. This is a code-and-unit-test fix only: recurring real execution,
GitHub queue continuity, and profitability are not guaranteed.
\n## 2026-11-08: Nonfatal full-margin risk-veto for explicitly armed repeating sessions

If the only chosen candidate requires more than the hard **10% of equity**
planned-loss limit while sizing up to 100% margin at 20x, the executor
**rejects that candidate without submitting a trade**. In separately
confirmed recurring mode, it reports `RISK_REJECTED_NO_ORDER` and the
worker continues monitoring and runs a new public signal scan after 5 seconds,
rather than crashing the GitHub session. Risk-limited **one-off** executions
still reject/stop, and **every other** exchange problem, invalid history,
uncertain execution response or protection failure still stops and requires
manual attention. The hard stop-risk invariant, size formula and ten-minute
post-exit cooldown are unchanged. Such rejected signals do not count as a
filled order; repeated scans do not guarantee a future eligible signal.

This prevents *this specific observed fatal workflow stop*, not all future
outages. The existing live workflow must be explicitly restarted after a
failed job; code commits alone cannot restart a failed live chain.


## General pre-order rejection classification and regression matrix

The recurring executor now differentiates **known, verified no-order candidate
rejections** from exchange/account/execution failures. Valid reasons include:
instrument inactive/unsupported, crossed or stale market, low liquidity turnover,
excessive spread, changed price after a scan, invalid LONG/SHORT stop/target,
initial stop outside 0.1%–3.5%, an impossible contract minimum under the existing
risk budget, excessive planned full-margin stop risk, or a *verified identical*
client order ID already present in exchange order history. Each is a hard veto
on that candidate. They return `CANDIDATE_REJECTED_NO_ORDER` or the pre-existing
`RISK_REJECTED_NO_ORDER`, and **only explicitly armed recurring mode** goes back
to fresh public scans. A valid report that simply expires during private
preflight yields `STALE_SIGNAL_NO_ORDER`; malformed timestamp reports still
fail closed. This does not change leverage, full-margin risk, TP/SL, or the
mandatory 10-minute cooldown. It cannot force trades.

Outages, missing account/position history, unexplained API responses, orders
whose status cannot be verified, missing TP/SL protection, or any other unknown
failure **still stop the worker** to avoid duplicate or unprotected orders.
GitHub Actions does not guarantee permanent 24/7 runners; no test suite can
guarantee that future API changes or outages never occur.


## Bounded runner and unknown-status hardening

When a **recurring** GitHub session has insufficient time remaining for the
last public market scan, a deadline-shortened public scan timeout is a clean
**no-order** handoff to the next session, rather than a false execution failure.
A full 90-second market scan timeout, account/monitor failure, private executor
timeout or unknown order state remains fatal. A confirmed one-off
`FILLED_PROTECTED` entry stops cleanly; any *unknown successful* executor status
now explicitly fails the GitHub job instead of silently marking it green while
abandoning the chain. The exchange-facing decision and order checks are intact.


## TITAN Omega (10 additive research roles) / isolated 20x

The user-requested 20x isolated leverage constant is implemented in `trading/okx_live_executor.py`. This multiplies both exposure and potential loss. Full-margin sizing remains separately armed and still rejects planned initial-stop loss above 10% of equity (realized losses can exceed it). Do not infer positive expectation from 2 days of PnL.

`trading/titan_omega.py` adds ten deterministic evidence roles: empirical stressed bootstrap of time-to-target; opposing/red-team flow and funding veto; exact one-of-N-or-WAIT QUBO-inspired opportunity ranking; indicative exchange cost twin; volatility-regime jump veto; observational causal-proxy panel (does not claim causal inference); empirical tails; walk-forward research task (NOT a trained self-rewriter); calibration quality task (NOT already calibrated); and SHA-256 public evidence fingerprints (NOT a persistent transaction ledger). Each role's actual scope is explicit in its output. Scores are *uncalibrated research heuristics*; simulation outcomes are not guaranteed probabilities. Existing 6+7 hard gates remain. The public scanner includes `omega_system_count: 10` and eligible candidates are ranked by Omega score, which emphasizes net modeled target improvement per time-to-target, or WAIT when unfavorable. No additional API trading permissions are granted.

The GitHub workflow requires Omega evidence (`OKX_REQUIRE_OMEGA=YES`) before any live execution attempt. Run in paper mode and check empirical forward results before any real trade. This is not a claim of verified quantum computation, a fully autonomous strategy laboratory, or guaranteed 24/7 hosting.

**STOP remains in force:** The GitHub execution workflow was disabled manually; `OKX_ENABLE_REAL_TRADING=NO` and `OKX_STOP_CONTINUOUS=YES`. Source-code updates do not re-enable real orders. A reliable persistent PnL and transaction ledger, independent exchange-risk daemon, and actual out-of-sample calibration are still required before unattended live 20x trading; Github's ephemeral runner is not persistent storage.


## 2026-11-11: Owner stop interlock + public research mode

The owner stopped LIVE trading and both stop flags are intentionally set: `OKX_ENABLE_REAL_TRADING=NO`, `OKX_STOP_CONTINUOUS=YES`. Earlier workflow runs requested `purpose=run`; they correctly failed at the authenticated monitor before any new order (`Live disabled: OKX_ENABLE_REAL_TRADING must be YES`). This is a safety stop, **not a reason to remove the guard or automatically resume trading**.

To safely test TITAN Omega, open the GitHub workflow **Run workflow** menu, select `purpose=research`, and leave all live confirmations unchecked. This option runs the public scanner and dry-run executor WITHOUT credentials, without authenticated balance access, without OKX POST calls, and without automatically chaining sessions. Public research artifacts can be downloaded from the run page. `purpose=validate` separately checks credentials using read-only OKX endpoints, without a trade.

Choosing `purpose=run` while owner stop switches remain active now fails early with an explicit actionable `STOP INTERLOCK` error before launching the continuous worker. A second independent check inside `check_mode` rejects real-money orders if the owner stop switch is YES; the chain step also stops if either flag is disabled. This is intentionally **fail-closed**, not a fake green live trading run. Tests cover the stop interlock, safe research selection, and guarding manual live runs. Live mode requires a separate explicit user decision to lift both stop switches; these patches do not change either flag.

The new ten Omega roles are experimental research diagnostics, not validated quantum algorithms. Persistent realized-PnL drawdown protection and open-position exchange reconciliation still need further engineering before safe unattended 20x/full-margin exposure.

## 2026-11-11: Adaptive 20x position sizing (the observed full-margin veto)

Repeated real runs at 12:08 UTC generated a legitimate Omega candidate but produced
`RISK_REJECTED_NO_ORDER` because full-margin 20x planned stop loss was >10% equity.
Rather than lower any risk-veto or force a market order, the new
`OKX_CAPITAL_MODE=adaptive_guarded` keeps the requested **20x isolated leverage**
and sizes **down** to a maximum planned **2% of available USDT equity at the initial stop**,
with **<=20% of available equity in initial isolated margin** and
**<=4x available equity in gross notional**. Stop risk is *estimated*, never a
maximum realized loss guarantee (gap, liquidation, slippage, fees, funding, platform
failure). It also clamps contracts to current OKX `max-size`, lot step and
minimum. If even the exchange minimum is too large, the candidate is rejected,
not force-filled. The historic `full_margin` mode and its 10% stop-risk veto
remain unchanged and independently armed for compatibility.

No changes to the 6-agent/7-system/10-Omega vetoes, no forced or guaranteed entries,
no change to protective TP/SL verification or 10-minute post-exit cooldown.
The workflow's runtime repository variable sets the selected allocation mode;
a job already running retains its start-of-run configuration. New job runs use
the updated variable. A persistent cumulative loss kill switch is still absent:
the strategy remains high-risk and should undergo forward testing before scaling.


## Optional real two-position guarded portfolio (not full-margin)
Use `OKX_MAX_ACTIVE_POSITIONS=2`, `OKX_PORTFOLIO_ARM=YES` only alongside
`OKX_CAPITAL_MODE=adaptive_guarded`, explicitly armed real execution and
the existing protected recurring worker. This is NOT an all-capital trading
promise: positions remain at most 2, combined planned-at-stop exposure <=5%
total equity, and combined approximate initial isolated margin <=50% equity,
with existing per-position <=2% stop risk and <=20% available equity margin.
The portfolio snapshot inspects current isolated SWAP positions and verifies
one complete TP/SL pair per position using authenticated read-only endpoints.
A second check immediately before entry verifies symbols and budget again.
Unknown protection, margin, balances or orders fail closed. Positions remain
open on the exchange even when GitHub Actions is stopped; stopping this
workflow does not close any position. Total loss can exceed estimated stops.
Do NOT enable live two-position mode until CI passes and a user explicitly
initiates the workflow with the real-trading confirmations.


## 2026-11-11: Diversified liquid-market rotation without forcing trades
Live recurring scans now rotate their public 12-symbol batch across the
entire approved, spread-limited, turnover >=15M USDT whitelist using
30-second time buckets. This prevents repeatedly searching only the highest
12 by turnover. The six-agent, seven-system and ten Omega proof gates,
market-data validity, equity sizing, leverage, risk limits, and real
trade confirmations are unchanged. A wider effective opportunity universe
does NOT imply a validated trading edge, 100% margin use, a profit target or
a guaranteed increase in executed trades. Each scan remains bounded at 12
symbols to respect existing GitHub Action time limits.


## 2026-11-11: Explicitly armed portfolio capacity up to 10 separate swap positions
The previously configured 2-position option accepts capacities 1 through 10
using GitHub Actions variable `OKX_MAX_ACTIVE_POSITIONS`. Capacities >1
require `OKX_PORTFOLIO_ARM=YES` and `OKX_CAPITAL_MODE=adaptive_guarded`.
Every open isolated USDT swap must have one verifiable TP+SL pair; missing,
orphaned or ambiguous exchange orders fail closed. A tenth qualifying
instrument may open while nine different symbols are held if remaining
risk/margin budget permits. An eleventh is blocked. **This is a maximum
capacity, not an instruction to trade without a qualifying signal.**
All positions together still have a **5%-of-equity planned-at-stop limit**
and **50%-of-equity initial isolated margin limit**. The position sizer
retains its separate 2%-at-stop and 20%-of-available-equity margin caps.
20x leverage remains high risk: stops do not guarantee realized-loss limits.
Never claim guaranteed or continuously fully invested performance; production
requires additional persistent drawdown monitoring and exchange reconciliation.


## 2026-11-11: Automatic discovery of *all* 20x-eligible OKX linear USDT perpetuals
The public scanner now loads `GET /api/v5/public/instruments?instType=SWAP`
**on every research scan**, builds an exchange-authoritative eligible universe,
and removes the manual coin allowlist. It admits only `state=live`,
`ctType=linear`, `settleCcy=USDT`, appropriate `ctValCcy`, normally
traded contracts with an advertised maximum leverage `lever >= 20`.
Market-selection retains strict >=15M USDT estimated 24h turnover and <=25bp
spread checks. Execution checks the same instrument fields and fresh max
leverage again before any 20x isolated position request; individual customer
limits and OKX can still block a 20x setting. The recurring worker rotates
through batches of **up to 12** candidates, so "all" means the eligible
universe is considered over successive scans, NOT that every coin is analyzed
at once or that every 20x contract is guaranteed a trade. Ten open positions
remain a maximum, not a target, and all existing aggregate risk limits are kept.
No weak/no-consensus orders are forced.


### Crypto category only
OKX also lists stock, ETF, forex, commodity and bond USDT swaps with 20x.
To implement the owner's request for **cryptocurrencies only**, the scanner and
fresh order preflight require `instCategory="1"`, OKX's documented crypto
asset class. The scanner rejects absent or unknown categories (fail closed)
rather than assuming every USDT-SWAP is cryptocurrency. Equity categories,
including highly liquid SOXL/SNDK, cannot become bot candidates.


## 2026-11-11: wider screened universe per cycle and granular veto diagnostics
The recurring LIVE worker now scans up to 20 verified high-turnover liquid
crypto 20x symbols each cycle (was 12), rotating across the exchange-qualified
universe. This increases candidate discovery without removing any six-agent,
seven-quant, ten Omega, spread, instrument, risk, leverage, stop, or cooldown
checks. Exact advanced/Omega veto reason counters are printed to logs so zero
trades can be traced to specific evidence gates. The scanner's 90-second
per-cycle timeout remains: exceptionally slow public APIs can still abort
the worker, and a live market order is NEVER forced for utilization goals.


## Audit: one filled order does not lock out remaining nine portfolio slots
The recurring worker enters exchange-state monitor after `FILLED_PROTECTED`.
A verified protected open position with remaining aggregate margin/risk
budget must produce `PORTFOLIO_ELIGIBLE`, not the old exclusive-position
waiting state. The next vetted scan may reach the executor for a DIFFERENT
market while the first position is still open. New regression tests cover
this path without placing orders. The monitor logs only `open`, `limit`,
and `remaining` slot counts, not sensitive balances or symbols.
Actual new orders still require independent signals, active protection,
risk budget, sufficient free equity, and valid exchange leverage.


## 2026-11-11: Single position, 30-second post-exit cooldown, separately armed full margin
The owner's updated plan replaces the 10-position portfolio target with
`OKX_MAX_ACTIVE_POSITIONS=1`. The executor and read-only monitor now enforce
the **same account-wide single-open-SWAP-position rule**; if a position exists,
the worker waits and cannot stack a second position. If a full close,
liquidation or ADL close is present in OKX authenticated
`/api/v5/account/positions-history`, the earliest *eligible* subsequent
entry is 30 seconds after the server-stamped close time. The monitor
checks the close state every 10 seconds during cooldown. Additional public
analysis and GitHub runner scheduling may delay the next trade; 30 seconds
is a minimum and **not a promised execution time**.
`OKX_CAPITAL_MODE=full_margin` is an optional account-risking allocation
up to available equity with isolated 20x leverage. It requires a separately
configured `OKX_FULL_MARGIN_ARM` secret and existing explicit live arming.
No 100% utilization or profit is guaranteed: a 10% planned stop-risk veto,
instrument limits, contract steps, fees, protection verification and weak
signals can refuse an entry. Liquidation, fees or slippage can cause a total
or greater-than-planned loss. No realized-drawdown kill switch has yet been
implemented, so unattended full-margin compounding carries significant
downside.


## 2026-11-11: One-cycle full 20x cryptocurrency universe screening
Public research and the explicitly armed LIVE workflow now pass
`--all-eligible` to the scanner. Every OKX instrument classified as
cryptocurrency and advertising >=20x for linear USDT swaps is screened
for fresh market turnover and bid/ask spread **within that cycle**.
All candidates passing existing >=15M USDT 24h volume and <=25 bp spread
requirements are deep-analyzed with 6 bounded concurrent public-data
workers (six original agents, seven quant systems, ten Omega diagnostics).
This replaces rolling slices of 20. Thin/spready contracts are *considered
and excluded*, never bought simply to achieve nominal 100% coverage.
The exchange's currently eligible instrument count can change over time.
The resulting report records total screened, deep candidates, completion
counts, and per-symbol errors; `read_report` refuses real execution if
a full-universe scan is partial or any API/data failure occurs.
Public calls still hit OKX rate limits, so a large universe or transient
errors can cause the 160s bounded public scan to fail closed without a
trade, instead of silently using a partial report. The bot keeps the
owner's existing single-position, 20x, 30-second minimum post-exit
cooldown, full-margin stop-risk veto, and protected-order checks.
This is not actual quantum computing, not a validated statistical edge,
and does not guarantee order placement or profits.


## 2026-11-11: Modest ordinal vote-lead relaxation, NOT forced entries
For the original 6-agent *core* proposal only, the directional score lead
threshold is now 1 (previously 2) ordinal point. An entry proposal still
requires at least two independent core directional voters, at least three
directional points, and zero liquidity/structure/stop safety vetoes.
Seven-system diagnostics still require at least **one independent directional
quantitative confirmation**, fewer than two opposing signals, and no risk
veto. The ten Omega diagnostics still reject non-positive model net edge
and excessive costs. Exchange-side order protection, 20x isolated leverage,
a maximum of one open position, adaptive guarded sizing, and the 30-second
minimum after a full exit are unchanged. More signals may be considered,
but no actual order or return is promised. Ordinal scores are NOT model
probabilities; the speculative strategy is not backtested to a verified edge.


## 2026-11-11: Public signal-funnel forensic audit (no trade behavior changes)
`trading/okx_signal_audit.py` reads only the research JSON from a completed
public scan, showing how many core directional candidates pass the independent
quantitative gate and Omega's net-cost/edge vetoes. Every LIVE/research GitHub
Actions job prints `TITAN AUDIT` counters, writes a public-only JSON artifact,
and shows a table in its GitHub job summary. It never reads OKX secrets,
credentials, position/order data or sends orders. A rejection at the seven-system
stage is NOT treated as an Omega pass simply because Omega was evaluated with
`WAIT`. This is transparent instrumentation, not backtesting. **Live strategy,
capital/risk limits, protected-order checks and confirmation thresholds are
unchanged.** Do not waive a hard safety gate simply to force order volume.


## 2026-11-11: Owner-requested 96% available-margin mode (stopped until manual start)
`OKX_CAPITAL_MODE=margin_96` targets **at most 96% of authenticated available
USDT isolated margin** as initial margin on one market order at **20x**
(approximately 19.2x the usable USDT balance in notional, before costs).
This is not 96% of total multi-asset account equity, and cannot guarantee
an exact allocation due to contract increments, fees, leverage restrictions
and exchange max-size. It does NOT adjust any existing OKX position.

This remains an exceptionally high liquidation-risk mode: only ~4% free
margin is targeted before fees/price movement, and even small adverse price
moves can rapidly erase the allocated margin. As with original `full_margin`,
separate `OKX_FULL_MARGIN_ARM` and all live authorization switches are
mandatory. The **existing 10% of available-equity planned stop-loss veto**
remains in place, so the bot will reject many otherwise valid signals
rather than force a 96%-margin trade when the required stop is wider.
Order protection, 20x limit, one-open-position-only, 30-second minimum
post-exit wait, all 6+7+10 signal gates, and duplicate-order and exchange
health preflights are unchanged. A newly started workflow must be manually
authorized; changing the configuration does not place trades. No verified
profit edge or hard realized-loss cap exists.
