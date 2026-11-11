#!/usr/bin/env python3
"""Guarded OKX USDT-perpetual execution adapter for 6-agent + QUANT2037 signals.

Default: read-only. Demo and live requests require separate explicit opt-ins.
Does not promise profitability. Designed for one execution attempt per workflow run.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trading.nvidia_execution_gate import GateRejected, _fresh_report

ALLOWED_DOMAINS = {'https://www.okx.com', 'https://eea.okx.com', 'https://us.okx.com'}
MODE_ARM = {'demo': 'CONFIRM_DEMO_ORDER', 'live': 'I_ACCEPT_REAL_MONEY_LOSS'}
CLIENT_PREFIX = 'Q37'
LEVERAGE = 20  # explicit user-requested isolated 20x; never computed from equity
MAX_LEVERAGE = 20
MIN_24H_TURNOVER_USDT = 15_000_000
MAX_SPREAD_BP = Decimal('15')
EQUITY_RISK_FRACTION = Decimal('0.0025')   # 0.25% account equity at initial stop, *not* guaranteed realised loss
NOTIONAL_CAP_FRACTION = Decimal('0.20')   # 20% equity notional cap
MARGIN_CAP_FRACTION = Decimal('0.05')     # 5% equity margin cap
REENTRY_COOLDOWN_MS = 30 * 1000  # minimum 30 seconds after exchange-confirmed full SWAP close
FULL_MARGIN_MODE = 'full_margin'  # Optional, independently armed; default stays guarded.
FULL_MARGIN_ARM = 'I_ACCEPT_FULL_MARGIN_LIQUIDATION_RISK'
MAX_FULL_MARGIN_PLANNED_STOP_RISK = Decimal('0.10')  # Refuse full-margin entries if planned stop exceeds 10% equity.
# Opt-in adaptive sizing: preserve 20x isolated leverage without deploying full margin.
# These are PLANNED initial-stop budgets, not caps on realized losses.
ADAPTIVE_GUARDED_MODE = 'adaptive_guarded'
ADAPTIVE_EQUITY_RISK_FRACTION = Decimal('0.02')  # <= 2% free USDT equity at initial stop
ADAPTIVE_MARGIN_CAP_FRACTION = Decimal('0.20')  # <= 20% of free USDT equity as isolated margin
ADAPTIVE_NOTIONAL_CAP_FRACTION = Decimal('4.0')  # <= 4x free USDT equity notional, despite 20x leverage

MAX_REPORT_AGE_S = 180
# OKX candle timestamps identify the OPEN of the 15-minute interval, not its close.
CANDLE_INTERVAL_MS = 15 * 60 * 1000
MAX_AGE_SINCE_CANDLE_CLOSE_MS = 15 * 60 * 1000


class ExecutionBlocked(RuntimeError):
    pass


class ReentryCooldownActive(ExecutionBlocked):
    """Verified exchange-side 10m wait; no trade may be submitted yet.

    Distinct from unknown OKX status, missing history, or other execution
    failures, which must still stop the worker rather than auto-retry.
    """


class CandidateRejected(ExecutionBlocked):
    """Deterministic pre-submit rejection; no /trade/order was attempted.

    Never use this for API/network errors, uncertain orders, unexpected
    account state, missing history, or post-submit protection failures.
    """


class OpportunityRiskRejected(CandidateRejected):
    """The local planned-loss invariant makes this candidate ineligible."""


class DuplicateCandidateRejected(CandidateRejected):
    """Exchange history confirms this exact client order id already exists."""


def dec(x):
    try:
        d = Decimal(str(x))
        if not d.is_finite():
            raise ValueError('Nonfinite input')
        return d
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ExecutionBlocked('Invalid decimal from data or instrument') from exc


def neat(d):
    return format(d.normalize(), 'f') if d != 0 else '0'


def floor_step(number, step):
    n, s = dec(number), dec(step)
    if s <= 0:
        raise ExecutionBlocked('Invalid instrument lot step')
    return (n / s).to_integral_value(rounding=ROUND_DOWN) * s


def tick_price(x, tick, rounding):
    d, t = dec(x), dec(tick)
    if d <= 0 or t <= 0:
        raise ExecutionBlocked('Invalid price or tick size')
    return (d / t).to_integral_value(rounding=rounding) * t


def check_mode(mode, env):
    if mode not in ('dry_run', 'demo', 'live'):
        raise ExecutionBlocked('Unsupported execution mode')
    capital_mode = env.get('OKX_CAPITAL_MODE', 'guarded').lower()
    if capital_mode not in ('guarded', ADAPTIVE_GUARDED_MODE, FULL_MARGIN_MODE):
        raise ExecutionBlocked('Unsupported capital allocation mode')
    if mode == 'dry_run':
        return
    if capital_mode == FULL_MARGIN_MODE and env.get('OKX_FULL_MARGIN_ARM') != FULL_MARGIN_ARM:
        raise ExecutionBlocked('Full-margin allocation not separately armed')
    slots_raw = env.get('OKX_MAX_ACTIVE_POSITIONS','1')
    from trading.okx_portfolio_guard import MAX_POSITIONS
    if not slots_raw.isdecimal() or not 1 <= int(slots_raw) <= MAX_POSITIONS:
        raise ExecutionBlocked('Maximum open positions must be between 1 and 10')
    if int(slots_raw) > 1:
        if (capital_mode != ADAPTIVE_GUARDED_MODE
                or env.get('OKX_PORTFOLIO_ARM') != 'YES'):
            raise ExecutionBlocked('Multi-position mode requires adaptive_guarded and separate portfolio arm')
    if env.get('OKX_EXECUTION_ARM') != MODE_ARM[mode]:
        raise ExecutionBlocked('Execution not armed: OKX_EXECUTION_ARM does not match selected mode')
    if mode == 'live' and env.get('OKX_ENABLE_REAL_TRADING') != 'YES':
        raise ExecutionBlocked('Live disabled: OKX_ENABLE_REAL_TRADING must be YES')
    if mode == 'live' and env.get('OKX_STOP_CONTINUOUS') == 'YES':
        raise ExecutionBlocked('Owner stop flag is active: OKX_STOP_CONTINUOUS=YES')
    if not all(env.get(k) for k in ('OKX_API_KEY','OKX_SECRET_KEY','OKX_PASSPHRASE')):
        raise ExecutionBlocked('Missing API credentials in environment (never put them in source code)')


class OKX:
    def __init__(self, env, *, transport=None):
        self.api_key = env.get('OKX_API_KEY', '')
        self.secret = env.get('OKX_SECRET_KEY', '')
        self.passphrase = env.get('OKX_PASSPHRASE', '')
        self.demo = env.get('OKX_EXECUTION_MODE') == 'demo'
        self.domain = env.get('OKX_API_DOMAIN', 'https://www.okx.com').rstrip('/')
        if self.domain not in ALLOWED_DOMAINS:
            raise ExecutionBlocked('Unsupported OKX API domain (whitelist only)')
        self.transport = transport

    def make_auth(self, method, request_path, body, at=None):
        timestamp = at or datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        prehash = timestamp + method + request_path + body
        signature = base64.b64encode(hmac.new(self.secret.encode(), prehash.encode(), hashlib.sha256).digest()).decode()
        return {'OK-ACCESS-KEY': self.api_key, 'OK-ACCESS-SIGN': signature,
                'OK-ACCESS-TIMESTAMP': timestamp, 'OK-ACCESS-PASSPHRASE': self.passphrase}

    def request(self, method, path, *, params=None, body=None, auth=True):
        if method not in ('GET','POST') or not path.startswith('/api/v5/'):
            raise ExecutionBlocked('Unexpected method or endpoint')
        if not auth and method != 'GET':
            raise ExecutionBlocked('Unauthenticated write rejected')
        query = '?' + urlencode(params) if params else ''
        request_path = path + query
        body_text = json.dumps(body, separators=(',', ':'), ensure_ascii=False) if body is not None else ''
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
                   'User-Agent': 'AgentEconomy-OKX-Live-Gated/1.0'}
        if auth:
            headers.update(self.make_auth(method, request_path, body_text))
        if self.demo:
            headers['x-simulated-trading'] = '1'
        request = {'method': method, 'url': self.domain + request_path,
                   'headers': headers, 'body': body_text}
        try:
            if self.transport:
                payload = self.transport(request)
            else:
                raw = body_text.encode() if body is not None else None
                req = Request(request['url'], data=raw, headers=headers, method=method)
                with urlopen(req, timeout=18) as response:
                    payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            # Never auto-retry POST /trade/order when response is unknown: it might have filled.
            raise ExecutionBlocked('OKX network error; check exchange state before retrying') from exc
        if not isinstance(payload, dict) or payload.get('code') != '0' or not isinstance(payload.get('data'), list):
            # Do not log raw server messages, which might echo request data.
            raise ExecutionBlocked('OKX rejected request at endpoint ' + path + '; code=' + str(payload.get('code') if isinstance(payload,dict) else '?'))
        return payload['data']


def read_report(path, now_ms=None):
    report = json.loads(Path(path).read_text(encoding='utf-8'))
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    if report.get('mode') != 'SIX_AGENTS_PLUS_SEVEN_QUANT_SYSTEMS_RESEARCH_ONLY':
        raise ExecutionBlocked('Unrecognized signal report mode')
    if report.get('core_specialist_agents') != 6 or report.get('advanced_quant_systems') != 7:
        raise ExecutionBlocked('Expected exactly six agents and seven systems')
    if report.get('errors'):
        raise ExecutionBlocked('Market scan had data errors; fail closed')
    timestamp = datetime.fromisoformat(report['utc_timestamp'].replace('Z', '+00:00'))
    age = now_ms / 1000 - timestamp.timestamp()
    if not 0 <= age < MAX_REPORT_AGE_S:
        raise ExecutionBlocked('Signal report is stale or from future')
    return report


def choose_signal(report, now_ms=None, *, exclude_symbols=()):
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    selected=[]
    for x in report.get('results', []):
        if x.get('signal') not in ('LONG','SHORT'):
            continue
        if x.get('advanced_system_count') != 7 or len(x.get('agents',[])) != 6:
            continue
        if x.get('advanced_veto_reasons') or x.get('derivatives_data_warnings'):
            continue
        if not x.get('advanced_confirmations',0) >= 1:
            continue
        if x.get('execution') != 'DISABLED' or x.get('order_count') != 0:
            continue
        price = dec(x.get('quote_price'))
        if price <= 0:
            continue
        ms = int(x.get('last_complete_15m_candle_ms') or 0)
        # A newly completed 15m candle was opened 15-30 minutes ago.
        # Rejecting candles 25m after OPEN spuriously vetoed signals in the
        # final five minutes of every 15m window.
        candle_close_ms = ms + CANDLE_INTERVAL_MS
        if not ms or not 0 <= now_ms-candle_close_ms <= MAX_AGE_SINCE_CANDLE_CLOSE_MS:
            continue
        symbol=x.get('symbol','')
        if symbol in exclude_symbols:
            continue
        if not symbol.endswith('-USDT-SWAP'):
            continue
        stop_data=x['agents'][-1]['evidence']
        stop, target=stop_data.get('indicative_stop_not_an_order'),stop_data.get('indicative_target_not_an_order')
        if stop is None or target is None:
            continue
        if x['signal']=='LONG' and not (0<dec(stop)<price<dec(target)):
            continue
        if x['signal']=='SHORT' and not (0<dec(target)<price<dec(stop)):
            continue
        # Only best consensus; one position at a time.
        margin = (x.get('ordinal_buy_points',0) - x.get('ordinal_sell_points',0)) if x['signal']=='LONG' else (x.get('ordinal_sell_points',0)-x.get('ordinal_buy_points',0))
        # Omega's one-of-N-or-WAIT QUBO score ranks faster, net-of-model-cost
        # target scenarios only when all 10 diagnostics are present and veto-free.
        # Compatibility: older research-only reports retain ordinal ordering.
        omega_count=x.get('omega_system_count')
        if omega_count is not None:
            if omega_count != 10 or x.get('omega_veto_reasons'):
                continue
            score=dec(x.get('omega_rank_score', 0))
            if score<=0:
                continue
            selected.append((score,margin,x))
            continue
        selected.append((Decimal(margin),margin,x))
    return max(selected,key=lambda k:(k[0],k[1]))[2] if selected else None


def estimate_turnover(ticker):
    price=dec(ticker.get('last'))
    base_vol=dec(ticker.get('volCcy24h'))
    return base_vol*price


def market_preflight(client, signal):
    symbol=signal['symbol']
    ticker=client.request('GET','/api/v5/market/ticker', params={'instId':symbol},auth=False)
    instruments=client.request('GET','/api/v5/public/instruments',params={'instType':'SWAP','instId':symbol},auth=False)
    if len(ticker)!=1 or len(instruments)!=1:
        raise ExecutionBlocked('Instrument information unavailable')
    t,inst=ticker[0],instruments[0]
    if t.get('instId')!=symbol or inst.get('instId')!=symbol or inst.get('state')!='live':
        raise CandidateRejected('Instrument inactive or mismatched')
    parts=symbol.split('-')
    if (len(parts)!=3 or parts[1:]!=['USDT','SWAP']
            or str(inst.get('instCategory',''))!='1'
            or inst.get('ctType')!='linear' or inst.get('settleCcy')!='USDT'
            or inst.get('ctValCcy')!=parts[0]
            or inst.get('ruleType') not in (None,'','normal')):
        raise CandidateRejected('Unsupported or pre-market contract')
    # The signal scan's leverage check is not an execution authorization.
    # Reconfirm public max leverage with a fresh instrument lookup before
    # modifying account leverage or placing a real order.
    try:
        advertised_max=dec(inst.get('lever','0'))
    except ExecutionBlocked as exc:
        raise CandidateRejected('Exchange maximum leverage not verifiable') from exc
    if advertised_max < LEVERAGE:
        raise CandidateRejected('Contract does not advertise 20x leverage')
    last,bid,ask=dec(t['last']),dec(t['bidPx']),dec(t['askPx'])
    if min(last,bid,ask)<=0 or bid>ask:
        raise CandidateRejected('Invalid or crossed market')
    if estimate_turnover(t) < MIN_24H_TURNOVER_USDT:
        raise CandidateRejected('Market turnover under 15,000,000 USD estimated')
    spread_bp=Decimal(10000)*(ask-bid)/((ask+bid)/2)
    if spread_bp > MAX_SPREAD_BP:
        raise CandidateRejected('Spread too wide')
    stamp=int(t.get('ts') or 0)
    if not stamp or not 0 <= int(time.time()*1000)-stamp <= 30_000:
        raise CandidateRejected('Ticker stale')
    scan_price=dec(signal['quote_price'])
    if abs(last/scan_price - 1)>Decimal('0.005'):
        raise CandidateRejected('Price moved >0.5% since analysis')
    return t,inst


def account_preflight(client):
    config=client.request('GET','/api/v5/account/config')
    if len(config)!=1 or config[0].get('posMode')!='net_mode':
        raise ExecutionBlocked('Account must be in net_mode; no automatic switch')
    # Use isolated USDT margin only; never sweep collateral or use full account.
    positions=client.request('GET','/api/v5/account/positions',params={'instType':'SWAP'})
    if any(dec(p.get('pos','0')) != 0 for p in positions):
        raise ExecutionBlocked('Another swap position exists; this bot manages one at most')
    pending=client.request('GET','/api/v5/trade/orders-pending',params={'instType':'SWAP'})
    if pending:
        raise ExecutionBlocked('Pending swap orders exist')
    for t in ('conditional','oco','trigger','move_order_stop'):
        algo=client.request('GET','/api/v5/trade/orders-algo-pending',params={'ordType':t})
        if any(z.get('instId','').endswith('-SWAP') for z in algo):
            raise ExecutionBlocked('Existing swap stop or algorithmic orders detected')
    balance=client.request('GET','/api/v5/account/balance',params={'ccy':'USDT'})
    if len(balance)!=1:
        raise ExecutionBlocked('Balance response not singular')
    total=dec(balance[0].get('totalEq'))
    usdrow=next((r for r in balance[0].get('details',[]) if r.get('ccy')=='USDT'),None)
    if not usdrow:
        raise ExecutionBlocked('USDT margin balance unavailable')
    free=dec(usdrow.get('availEq') or usdrow.get('availBal') or '0')
    if total<=0 or free<=0:
        raise ExecutionBlocked('No positive USDT available equity')
    return min(total,free)


def daily_order_limit(client, *, now_ms=None, candidate_id=None):
    """Fail closed if full last-24h order history cannot be verified.

    This is an order-frequency guard, not a genuine realized PnL/drawdown monitor.
    """
    now_ms=int(time.time()*1000) if now_ms is None else now_ms
    cutoff=now_ms-86_400_000
    cursor=None
    bot_orders=set()
    for _ in range(20):
        params={'instType':'SWAP','limit':'100'}
        if cursor:params['after']=cursor
        rows=client.request('GET','/api/v5/trade/orders-history',params=params)
        if not rows:
            return len(bot_orders)
        for row in rows:
            created=int(row.get('cTime') or row.get('uTime') or 0)
            if created>=cutoff:
                if candidate_id and row.get('clOrdId')==candidate_id:
                    raise DuplicateCandidateRejected('Same client order ID already exists in 24h history')
                if str(row.get('clOrdId','')).startswith(CLIENT_PREFIX):
                    bot_orders.add(row.get('clOrdId'))
        oldest=min(int(z.get('cTime') or z.get('uTime') or 0) for z in rows)
        if oldest < cutoff or len(rows)<100:
            return len(bot_orders)
        cursor=rows[-1].get('ordId')
        if not cursor:
            raise ExecutionBlocked('Cannot paginate order history safely')
    raise ExecutionBlocked('Order history too long; refuse trade')


def enforce_exit_cooldown(client, *, now_ms=None):
    """Block all new entries for 30 seconds after a full SWAP close or liquidation.

    Reads OKX's durable exchange-side position history, so a GitHub runner
    restarting does not erase the cooldown. Never infer exits from an absent
    open position or the order's creation time.
    """
    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    rows = client.request('GET', '/api/v5/account/positions-history',
                          params={'instType': 'SWAP', 'limit': '100'})
    if not isinstance(rows, list):
        raise ExecutionBlocked('Cannot verify latest SWAP close time')
    cutoff = now_ms - REENTRY_COOLDOWN_MS
    seen_times = []
    for row in rows:
        if row.get('instType', 'SWAP') != 'SWAP':
            continue
        try:
            updated = int(row.get('uTime') or '0')
        except (ValueError, TypeError) as exc:
            raise ExecutionBlocked('Invalid timestamp in SWAP position history') from exc
        if updated <= 0 or updated > now_ms + 60_000:
            raise ExecutionBlocked('Missing or future SWAP position-history timestamp')
        seen_times.append(updated)
        # 2 = fully closed; 3 = liquidation; 6 = ADL full close.
        # Partial closes don't release the bot to enter a new coin.
        if str(row.get('type')) in ('2', '3', '6') and updated > cutoff:
            remaining = (updated + REENTRY_COOLDOWN_MS - now_ms + 999) // 1000
            raise ReentryCooldownActive('Re-entry cooldown active after SWAP exit; at least ' +
                                        str(remaining) + ' seconds remain')
    if len(rows) >= 100 and seen_times and min(seen_times) > cutoff:
        # A full first page that does not cover the entire window is ambiguous.
        raise ExecutionBlocked('Position-history pagination needed: cooldown status unverified')
    return True


def get_prices(signal,ticker,inst):
    last=dec(ticker['last'])
    tick=dec(inst['tickSz'])
    risk=signal['agents'][-1]['evidence']
    proposed_stop=dec(risk['indicative_stop_not_an_order'])
    proposed_target=dec(risk['indicative_target_not_an_order'])
    if signal['signal']=='LONG':
        price=dec(ticker['askPx'])
        stop=tick_price(proposed_stop,tick,ROUND_DOWN)
        target=tick_price(proposed_target,tick,ROUND_UP)
        if not (stop < last < target and stop<price<target):
            raise CandidateRejected('Invalid LONG stop/target after price refresh')
        delta=(price-stop)/price
    else:
        price=dec(ticker['bidPx'])
        stop=tick_price(proposed_stop,tick,ROUND_UP)
        target=tick_price(proposed_target,tick,ROUND_DOWN)
        if not (target < last < stop and target<price<stop):
            raise CandidateRejected('Invalid SHORT stop/target after price refresh')
        delta=(stop-price)/price
    if not Decimal('0.001') <= delta <= Decimal('0.035'):
        raise CandidateRejected('Stop outside approved 0.1% to 3.5% distance')
    return price,stop,target,delta


def contract_size(inst, price, equity, stop_fraction, *, capital_mode='guarded', exchange_max=None):
    """Determine contract quantity; full-margin mode needs an independently armed execution path.

    Full-margin target is up to 100% of *available* USDT isolated margin at 20x,
    subject to exchange max size, lot step, planned-stop budget and trading fees.
    This is NOT a maximum-realized-loss guarantee.
    """
    multiplier=dec(inst['ctVal'])
    lot=dec(inst['lotSz']); minimum=dec(inst['minSz'])
    price=dec(price); equity=dec(equity); stop_fraction=dec(stop_fraction)
    if multiplier<=0 or min(lot,minimum)<=0 or min(price,equity,stop_fraction)<=0:
        raise ExecutionBlocked('Invalid contract specifications or capital inputs')
    per_contract=multiplier*price
    if capital_mode == FULL_MARGIN_MODE:
        if exchange_max is None:
            raise ExecutionBlocked('Full-margin mode requires fresh OKX max-size quote')
        exchange_limit=dec(exchange_max)
        if exchange_limit <= 0:
            raise ExecutionBlocked('Exchange reports no available full-margin order capacity')
        max_notional = equity * LEVERAGE
        contracts = floor_step(min(max_notional / per_contract, exchange_limit), lot)
        if contracts < minimum or contracts <= 0:
            raise CandidateRejected('Full-margin quantity is below exchange minimum')
        intended_stop_loss = contracts * per_contract * stop_fraction
        if intended_stop_loss > equity * MAX_FULL_MARGIN_PLANNED_STOP_RISK:
            raise OpportunityRiskRejected('Full-margin stop implies over 10% equity planned loss; refuse order')
        if contracts * per_contract > equity * LEVERAGE:
            raise ExecutionBlocked('Full-margin leverage invariant failed')
        return contracts
    if capital_mode == ADAPTIVE_GUARDED_MODE:
        # Size down to respect stop loss instead of refusing a whole-margin
        # position that violates the planned risk budget.
        if exchange_max is None:
            raise ExecutionBlocked('Adaptive sizing requires a fresh OKX max-size quote')
        exchange_limit=dec(exchange_max)
        if exchange_limit<=0:
            raise CandidateRejected('OKX reports no capacity for adaptive position')
        notional_budget=min(equity*ADAPTIVE_EQUITY_RISK_FRACTION/stop_fraction,
                            equity*ADAPTIVE_NOTIONAL_CAP_FRACTION,
                            equity*ADAPTIVE_MARGIN_CAP_FRACTION*LEVERAGE)
        contracts=floor_step(min(notional_budget/per_contract,exchange_limit),lot)
        if contracts < minimum or contracts<=0:
            raise CandidateRejected('Adaptive risk budget cannot cover exchange minimum; no order')
        notional=contracts*per_contract
        if notional*stop_fraction > equity*ADAPTIVE_EQUITY_RISK_FRACTION:
            raise ExecutionBlocked('Adaptive per-stop equity-risk invariant failed')
        if notional > equity*ADAPTIVE_NOTIONAL_CAP_FRACTION:
            raise ExecutionBlocked('Adaptive gross-notional invariant failed')
        if notional/LEVERAGE > equity*ADAPTIVE_MARGIN_CAP_FRACTION:
            raise ExecutionBlocked('Adaptive isolated-margin invariant failed')
        if contracts>exchange_limit:
            raise ExecutionBlocked('Adaptive exchange max-size invariant failed')
        return contracts
    if capital_mode != 'guarded':
        raise ExecutionBlocked('Unknown capital allocation')
    max_notional=min(equity*EQUITY_RISK_FRACTION/stop_fraction,
                     equity*NOTIONAL_CAP_FRACTION,
                     equity*MARGIN_CAP_FRACTION*LEVERAGE)
    contracts=floor_step(max_notional/per_contract,lot)
    if contracts<minimum or contracts<=0:
        raise CandidateRejected('Risk budget smaller than minimum exchange contract; do not oversize')
    if contracts*per_contract*stop_fraction>equity*EQUITY_RISK_FRACTION:
        raise ExecutionBlocked('Risk invariant failed')
    return contracts


def client_order_id(signal):
    symbol=signal['symbol']
    candle=str(signal['last_complete_15m_candle_ms'])
    key=f'{symbol}|{candle}|{signal["signal"]}'.encode()
    return CLIENT_PREFIX + hashlib.sha256(key).hexdigest()[:26]


def emergency_flatten(client, signal, clordid):
    """Best-effort flatten newly opened position. Cannot promise a fill."""
    symbol=signal['symbol']
    pos=client.request('GET','/api/v5/account/positions',params={'instType':'SWAP','instId':symbol})
    qty=sum(abs(dec(p.get('pos','0'))) for p in pos)
    if qty<=0:
        return 'NO_POSITION_FOUND'
    side='sell' if signal['signal']=='LONG' else 'buy'
    close=client.request('POST','/api/v5/trade/order',body={
        'instId':symbol,'tdMode':'isolated','posSide':'net','side':side,
        'ordType':'market','sz':neat(qty),'reduceOnly':True,
        'clOrdId':CLIENT_PREFIX+'EM'+hashlib.sha256((clordid+'EXIT').encode()).hexdigest()[:24]})
    if not close or close[0].get('sCode')!='0':
        raise ExecutionBlocked('Emergency reduce-only close request rejected by exchange')
    return 'EMERGENCY_CLOSE_REQUESTED'


def _abort_uncertain_post_submit(client, signal, clordid, reason):
    """Attempt a reduce-only emergency close if post-submit state is uncertain.

    Never assume an unconfirmed fill has disappeared. A closure is best-effort
    and must be inspected on the exchange; this function never claims success.
    It is called only AFTER the original entry order was submitted.
    """
    try:
        outcome = emergency_flatten(client, signal, clordid)
    except Exception as exc:
        raise ExecutionBlocked(
            'URGENT: ' + reason + '; emergency close could not be verified; inspect OKX immediately'
        ) from exc
    raise ExecutionBlocked(
        'URGENT: ' + reason + '; emergency recovery=' + outcome +
        '; inspect OKX position and protective orders immediately'
    )


def inspect_after_submit(client,signal,clordid):
    """Check that position appears and native protective orders exist; fail closed.

    If protection was not confirmed, attempt emergency flatten. That flatten can
    itself fail due to exchange/network outages; operator must monitor OKX directly.
    """
    symbol=signal['symbol']
    order_detail=None
    for _ in range(4):
        time.sleep(1)
        try:
            order_list=client.request('GET','/api/v5/trade/order',params={'instId':symbol,'clOrdId':clordid})
        except Exception:
            _abort_uncertain_post_submit(client, signal, clordid,
                                         'Entry order status could not be read')
        if order_list:
            order_detail=order_list[0]
            if order_detail.get('state') in ('filled','canceled'):
                break
    if order_detail is None:
        _abort_uncertain_post_submit(client, signal, clordid,
                                     'Entry order confirmation unavailable')
    if order_detail.get('state') != 'filled':
        # A market order may be partially filled. Cancel any outstanding remainder,
        # then attempt to flatten the actual position instead of assuming zero exposure.
        try:
            if order_detail.get('state') in ('live','partially_filled'):
                client.request('POST','/api/v5/trade/cancel-order',body={
                    'instId':symbol,'clOrdId':clordid})
            emergency_flatten(client,signal,clordid)
        except Exception as exc:
            raise ExecutionBlocked('URGENT: partial/unfilled order and flatten not confirmed; inspect OKX') from exc
        raise ExecutionBlocked('Market order not completely filled; emergency flatten attempted, inspect OKX')
    protected=False
    for _ in range(4):
        try:
            algo_rows=client.request('GET','/api/v5/trade/orders-algo-pending',params={'ordType':'oco'})
            algo_rows+=client.request('GET','/api/v5/trade/orders-algo-pending',params={'ordType':'conditional'})
        except Exception:
            _abort_uncertain_post_submit(client, signal, clordid,
                                         'Protective order status could not be read')
        for row in algo_rows:
            if row.get('instId')==symbol and row.get('slTriggerPx') and row.get('tpTriggerPx'):
                protected=True
        if protected:break
        time.sleep(1)
    if protected:
        return 'FILLED_PROTECTED'
    # An attached TP/SL may be split into separate algo orders; this check intentionally
    # fails closed rather than trusting a partially observed protection state.
    try:
        emergency_flatten(client,signal,clordid)
    except Exception as exc:
        raise ExecutionBlocked('URGENT: protection unverified and emergency flatten failed; inspect OKX') from exc
    raise ExecutionBlocked('TP/SL could not be confirmed; emergency close requested, verify OKX position')


def execute(report, client, mode, env, *, allow_post=True):
    check_mode(mode,env)
    # Explicitly armed full_margin remains protected by check_mode's separate
    # full-margin arm, contract_size's 10%-planned-stop-risk rejection, and all
    # original exchange-side checks. No fixed 24h entry count is imposed.
    # When explicitly requested by the GitHub worker, old non-Omega reports
    # must never bypass the new proof/optimization gate in live execution.
    if env.get('OKX_REQUIRE_OMEGA') == 'YES':
        if report.get('omega_system_count') != 10:
            raise ExecutionBlocked('Missing TITAN Omega 10-system research report')
        for item in report.get('results', []):
            if item.get('signal') in ('LONG','SHORT') and item.get('omega_system_count') != 10:
                raise ExecutionBlocked('Candidate lacks verified TITAN Omega evidence')
    signal=choose_signal(report)
    if signal is None:
        return 'NO_CONSENSUS'
    # Dry-run stays public-only, even with portfolio settings.
    if mode=='dry_run':
        return 'DRY_RUN_SIGNAL_ONLY'
    max_positions = int(env.get('OKX_MAX_ACTIVE_POSITIONS','1'))
    multi = max_positions > 1
    account_before = None
    if multi:
        from trading.okx_portfolio_guard import snapshot, UnsafePortfolio
        try:
            account_before=snapshot(client)
        except UnsafePortfolio as exc:
            raise ExecutionBlocked('Portfolio validation failed: '+str(exc)) from exc
        if len(account_before['symbols']) >= max_positions:
            return 'PORTFOLIO_CAPACITY_NO_ORDER'
        signal=choose_signal(report,exclude_symbols=account_before['symbols'])
        if signal is None:
            return 'NO_CONSENSUS'
    # NVIDIA research is isolated in okx-nvidia-advisory.yml: never imported,
    # queried, or evaluated in the execution/order path. Quantitative signals
    # and mandatory exchange-side risk controls remain the only entry gates.
    try:
        ticker,inst=market_preflight(client,signal)
    except CandidateRejected:
        if env.get('OKX_AUTOREENTRY_ENABLED') == 'YES':
            return 'CANDIDATE_REJECTED_NO_ORDER'
        raise
    if multi:
        from trading.okx_portfolio_guard import sizing_equity
        equity=sizing_equity(account_before)
        if equity<=0:
            return 'RISK_REJECTED_NO_ORDER'
    else:
        equity=account_preflight(client)
    try:
        enforce_exit_cooldown(client)
    except ReentryCooldownActive:
        # This is a verified no-order wait, NOT an order failure. Only the
        # separately armed recurring worker may continue polling; do not ever
        # treat other ExecutionBlocked/network/history errors as recoverable.
        if env.get('OKX_AUTOREENTRY_ENABLED') == 'YES':
            return 'REENTRY_COOLDOWN_NO_ORDER'
        raise
    clordid=client_order_id(signal)
    # Check the latest 24h history for duplicate client order IDs, not a numeric trade limit.
    # A second entry is only considered after the exchange-verified 30-second exit cooldown.
    try:
        daily_order_limit(client,candidate_id=clordid)  # Exchange-confirmed anti-replay.
    except DuplicateCandidateRejected:
        if env.get('OKX_AUTOREENTRY_ENABLED') == 'YES':
            return 'CANDIDATE_REJECTED_NO_ORDER'
        raise
    try:
        price,stop,target,stop_fraction=get_prices(signal,ticker,inst)
    except CandidateRejected:
        if env.get('OKX_AUTOREENTRY_ENABLED') == 'YES':
            return 'CANDIDATE_REJECTED_NO_ORDER'
        raise
    capital_mode=env.get('OKX_CAPITAL_MODE','guarded').lower()
    # Verify OKX exchange size limit; leverage config changed only at last possible step.
    client.request('POST','/api/v5/account/set-leverage',body={
        'instId':signal['symbol'],'lever':str(LEVERAGE),'mgnMode':'isolated'})
    allowed=client.request('GET','/api/v5/account/max-size',params={
        'instId':signal['symbol'],'tdMode':'isolated'})
    if len(allowed)!=1:
        raise ExecutionBlocked('Max-size quote unavailable')
    max_side='maxBuy' if signal['signal']=='LONG' else 'maxSell'
    try:
        contracts=contract_size(inst,price,equity,stop_fraction,
            capital_mode=capital_mode,exchange_max=allowed[0].get(max_side,'0'))
    except CandidateRejected as exc:
        # Only deterministic candidate vetoes are skippable. Never reduce the
        # allocated risk/stop limits or reuse a rejected order in this scan.
        if env.get('OKX_AUTOREENTRY_ENABLED') == 'YES':
            return ('RISK_REJECTED_NO_ORDER' if isinstance(exc,OpportunityRiskRejected)
                    else 'CANDIDATE_REJECTED_NO_ORDER')
        raise
    if multi:
        from trading.okx_portfolio_guard import check_new, UnsafePortfolio
        try:
            check_new(account_before,contracts*dec(inst['ctVal'])*price,stop_fraction)
        except UnsafePortfolio:
            if env.get('OKX_AUTOREENTRY_ENABLED') == 'YES':
                return 'RISK_REJECTED_NO_ORDER'
            raise
    if contracts > dec(allowed[0].get(max_side,'0')):
        raise ExecutionBlocked('Insufficient exchange margin for sized order')
    # Re-check bot order frequency and open positions immediately before placing.
    try:
        daily_order_limit(client,candidate_id=clordid)  # Final anti-replay, before POST.
    except DuplicateCandidateRejected:
        if env.get('OKX_AUTOREENTRY_ENABLED') == 'YES':
            return 'CANDIDATE_REJECTED_NO_ORDER'
        raise
    if multi:
        # Re-fetch every exposure/protective order directly from OKX near submit.
        from trading.okx_portfolio_guard import snapshot, check_new, UnsafePortfolio
        try:
            latest=snapshot(client)
            if latest['symbols']!=account_before['symbols']:
                raise ExecutionBlocked('Portfolio changed since first account snapshot')
            check_new(latest,contracts*dec(inst['ctVal'])*price,stop_fraction)
        except UnsafePortfolio as exc:
            raise ExecutionBlocked('Pre-order portfolio veto: '+str(exc)) from exc
    else:
        if any(dec(x.get('pos','0')) for x in client.request('GET','/api/v5/account/positions',params={'instType':'SWAP'})):
            raise ExecutionBlocked('Position changed before order placement')
        if client.request('GET','/api/v5/trade/orders-pending',params={'instType':'SWAP'}):
            raise ExecutionBlocked('Orders appeared before placement')
    try:
        enforce_exit_cooldown(client)  # Re-check immediately before any live or demo order.
    except ReentryCooldownActive:
        if env.get('OKX_AUTOREENTRY_ENABLED') == 'YES':
            return 'REENTRY_COOLDOWN_NO_ORDER'
        raise
    # Never place an order using research that expired while private OKX
    # preflight checks were running.
    try:
        _fresh_report(report)
    except GateRejected as exc:
        # An expired but well-formed report can be replaced with a fresh scan.
        # Malformed/missing timestamps remain fatal; never guess freshness.
        if (env.get('OKX_AUTOREENTRY_ENABLED') == 'YES'
                and str(exc) == 'Market report expired during NVIDIA review'):
            return 'STALE_SIGNAL_NO_ORDER'
        raise ExecutionBlocked('Freshness veto: ' + str(exc)) from exc
    if not allow_post:
        return 'PREPARED_BUT_NOT_SENT'
    payload={
        'instId':signal['symbol'],'tdMode':'isolated','posSide':'net',
        'side':'buy' if signal['signal']=='LONG' else 'sell',
        'ordType':'market','sz':neat(contracts),'clOrdId':clordid,
        'attachAlgoOrds':[{
            'tpTriggerPx':neat(target),'tpOrdPx':'-1','tpTriggerPxType':'mark',
            'slTriggerPx':neat(stop),'slOrdPx':'-1','slTriggerPxType':'mark'
        }]
    }
    response=client.request('POST','/api/v5/trade/order',body=payload)
    if len(response)!=1 or response[0].get('sCode')!='0':
        raise ExecutionBlocked('Order was rejected by exchange; no automatic retries')
    return inspect_after_submit(client,signal,clordid)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',default='reports/okx_six_agents.json')
    parser.add_argument('--mode',choices=['dry_run','demo','live'],default=os.environ.get('OKX_EXECUTION_MODE','dry_run'))
    parser.add_argument('--verify-only',action='store_true',help='Authenticate and check account config; never trade')
    args=parser.parse_args()
    try:
        env=dict(os.environ)
        env['OKX_EXECUTION_MODE']=args.mode
        if args.verify_only:
            if not all(env.get(k) for k in ('OKX_API_KEY','OKX_SECRET_KEY','OKX_PASSPHRASE')):
                raise ExecutionBlocked('Cannot verify: encrypted OKX API secrets are missing')
            # Validate exact live/full-margin arming without posting any orders.
            # A missing or mismatched repository secret fails the dry validation
            # before anyone attempts an unattended LIVE workflow.
            if args.mode in ('live','demo'):
                check_mode(args.mode,env)
            client=OKX(env)
            config=client.request('GET','/api/v5/account/config')
            if len(config)!=1:
                raise ExecutionBlocked('Unexpected account configuration response')
            # Verify the documented exchange-side exit-history feed without any trading rights.
            history=client.request('GET','/api/v5/account/positions-history',
                                   params={'instType':'SWAP','limit':'100'})
            if not isinstance(history,list):
                raise ExecutionBlocked('Position history unavailable: do not activate real orders')
            try:
                enforce_exit_cooldown(client)
                reentry='ELIGIBLE_BY_EXIT_TIME_ONLY'
            except ReentryCooldownActive:
                reentry='COOLDOWN_ACTIVE'
            print('OKX connection verified; account mode:', config[0].get('posMode','unknown'),
                  '; exit-history feed verified; re-entry:', reentry, '; NO ORDERS')
            return 0
        check_mode(args.mode,env)
        report=read_report(args.report)
        status=execute(report,OKX(env),args.mode,env)
        # Do not print balances, keys, client order ids or exact position sizes in public Actions logs.
        print('OKX EXECUTION RESULT:',status)
        return 0
    except ExecutionBlocked as exc:
        print('OKX EXECUTION BLOCKED:',str(exc),file=sys.stderr)
        return 2
    except Exception:
        print('OKX EXECUTION ERROR: no blind retry; inspect exchange account state',file=sys.stderr)
        return 3


if __name__=='__main__':
    raise SystemExit(main())
