"""TITAN MicroSpot guarded live order executor.

Optional real OKX SPOT cash trade; **never** submits margin/derivative orders.
Operates one entry + exchange-native OCO protection per run. Unsafe, ambiguous
or stale conditions fail CLOSED. Not a trading-profit or stop-loss guarantee.
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
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trading.microspot_scout import cash_plan, dec, floor_step, scan, public_get

DOMAIN = 'https://www.okx.com'
ALLOWED_GET = frozenset({
    '/api/v5/account/positions', '/api/v5/account/balance',
    '/api/v5/trade/orders-pending', '/api/v5/trade/orders-algo-pending',
    '/api/v5/trade/order',
})
ALLOWED_POST = frozenset({'/api/v5/trade/order', '/api/v5/trade/order-algo'})
MAX_USDT_ALLOC = Decimal('0.90')  # 10% buffer in cash; not a risk-at-stop guarantee
MAX_SPREAD_PCT = Decimal('0.25')
STOP_PCT = Decimal('0.02')
TARGET_PCT = Decimal('0.05')
MAX_ORDER_USDT = Decimal('200')  # cap accidentally large account exposure


class SpotHalt(RuntimeError):
    """Stop new orders and require account review where indicated."""


def fmt(value):
    return format(dec(value).normalize(), 'f')


def price_step(value, tick, *, up=False):
    val, t = dec(value), dec(tick)
    if t <= 0 or val <= 0:
        raise SpotHalt('invalid tick/price')
    method = ROUND_CEILING if up else ROUND_FLOOR
    return (val / t).to_integral_value(rounding=method) * t


class OKXCash:
    def __init__(self, env):
        if env.get('OKX_API_DOMAIN', DOMAIN).rstrip('/') != DOMAIN:
            raise SpotHalt('unapproved OKX endpoint')
        self.key = env.get('OKX_API_KEY', '')
        self.secret = env.get('OKX_SECRET_KEY', '')
        self.passphrase = env.get('OKX_PASSPHRASE', '')
        if not (self.key and self.secret and self.passphrase):
            raise SpotHalt('missing OKX credentials')

    def request(self, method, path, *, params=None, body=None):
        if method == 'GET' and path in ALLOWED_GET and body is None:
            pass
        elif method == 'POST' and path in ALLOWED_POST and params is None and isinstance(body, dict):
            if body.get('tdMode') != 'cash' or not body.get('instId', '').endswith('-USDT'):
                raise SpotHalt('refused non-cash/non-SPOT order')
            if body.get('side') not in ('buy', 'sell'):
                raise SpotHalt('invalid side')
            if path.endswith('/order') and (body.get('ordType') != 'market'
                                                or body.get('tgtCcy') not in ('quote_ccy', 'base_ccy')):
                raise SpotHalt('only SPOT cash market entries/exits allowed')
            if path.endswith('/order-algo') and (body.get('ordType') != 'oco'
                                                     or body.get('side') != 'sell'):
                raise SpotHalt('only SPOT cash protective SELL OCO allowed')
        else:
            raise SpotHalt('private endpoint/method not allowlisted')
        query = ('?' + urlencode(params)) if params else ''
        payload = json.dumps(body, separators=(',', ':')) if body is not None else ''
        timestamp = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        canonical = timestamp + method + path + query + payload
        sign = base64.b64encode(hmac.new(self.secret.encode(), canonical.encode(), hashlib.sha256).digest()).decode()
        headers = {'OK-ACCESS-KEY': self.key, 'OK-ACCESS-SIGN': sign,
                   'OK-ACCESS-TIMESTAMP': timestamp, 'OK-ACCESS-PASSPHRASE': self.passphrase,
                   'Content-Type': 'application/json'}
        req = Request(DOMAIN + path + query, headers=headers,
                      data=(payload.encode() if method == 'POST' else None), method=method)
        # For a POST networking error, execution is UNCERTAIN. Never retry it automatically.
        try:
            with urlopen(req, timeout=15) as resp:
                result = json.load(resp)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            raise SpotHalt('private API response unavailable; inspect OKX; NO BLIND RETRY') from exc
        if (not isinstance(result, dict) or str(result.get('code')) != '0'
                or not isinstance(result.get('data'), list)):
            raise SpotHalt('OKX rejected/ambiguous response; inspect OKX')
        if method == 'POST' and (len(result['data']) != 1 or str(result['data'][0].get('sCode')) != '0'):
            raise SpotHalt('OKX rejected order; inspect OKX')
        return result['data']


def available(client, ccy):
    balance = client.request('GET', '/api/v5/account/balance', params={'ccy': ccy})
    if len(balance) != 1 or not isinstance(balance[0].get('details'), list):
        raise SpotHalt('cannot verify available cash')
    matches = [r for r in balance[0]['details'] if r.get('ccy') == ccy]
    if not matches and ccy != 'USDT':
        return Decimal('0')  # An asset with zero balance may be absent from details.
    if len(matches) != 1:
        raise SpotHalt('cash currency not uniquely verified')
    row = matches[0]
    if dec(row.get('liab') or '0') != 0:
        raise SpotHalt('borrowed balance detected')
    avail = dec(row.get('availBal') or '0')
    if avail < 0:
        raise SpotHalt('negative available balance')
    return avail


def no_derivatives_or_open_orders(client):
    positions = client.request('GET', '/api/v5/account/positions')
    if not isinstance(positions, list):
        raise SpotHalt('position feed not verified')
    for r in positions:
        if dec(r.get('pos', '0')) != 0:
            raise SpotHalt('existing margin/futures/swap exposure: verify or close in OKX first')
    # Do not touch a pre-existing order, including another trader's orders.
    for kind in ('SPOT', 'SWAP', 'MARGIN', 'FUTURES'):
        if client.request('GET', '/api/v5/trade/orders-pending', params={'instType': kind}):
            raise SpotHalt('existing pending orders: account review required')
    for kind in ('oco', 'conditional', 'trigger', 'move_order_stop'):
        if client.request('GET', '/api/v5/trade/orders-algo-pending', params={'ordType': kind}):
            raise SpotHalt('existing protective/conditional orders: account review required')


def instrument(symbol):
    rows = public_get('/api/v5/public/instruments', {'instType':'SPOT','instId':symbol})
    matches = [r for r in rows if r.get('instId') == symbol and r.get('state') == 'live']
    if len(matches) != 1:
        raise SpotHalt('SPOT instrument not live/verified')
    return matches[0]


def fresh_ticker(symbol):
    rows = public_get('/api/v5/market/ticker', {'instId':symbol})
    if len(rows) != 1 or rows[0].get('instId') != symbol:
        raise SpotHalt('ticker unavailable')
    tick = rows[0]
    bid, ask = dec(tick.get('bidPx')), dec(tick.get('askPx'))
    if bid <= 0 or ask <= bid or (ask - bid) / ask * 100 > MAX_SPREAD_PCT:
        raise SpotHalt('invalid/wide SPOT spread')
    ts = int(tick.get('ts', 0))
    if not 0 <= time.time() * 1000 - ts <= 20000:
        raise SpotHalt('SPOT ticker not fresh')
    return ask, bid


def entry_body(symbol, quote_budget, token):
    # OKX market spot buy with quote_ccy spends USDT; no leverage or borrow.
    if not symbol.endswith('-USDT') or quote_budget <= 0:
        raise SpotHalt('invalid cash entry')
    return {'instId': symbol, 'tdMode': 'cash', 'side': 'buy',
            'ordType': 'market', 'tgtCcy': 'quote_ccy', 'sz': fmt(quote_budget),
            'clOrdId': token}


def protect_body(symbol, qty, avg_px, tick, lot, token):
    qty = floor_step(qty, lot)
    if qty <= 0:
        raise SpotHalt('no protectable purchased quantity')
    tp = price_step(dec(avg_px) * (1 + TARGET_PCT), tick, up=True)
    sl = price_step(dec(avg_px) * (1 - STOP_PCT), tick, up=False)
    if not 0 < sl < dec(avg_px) < tp:
        raise SpotHalt('invalid protection prices')
    return {'instId': symbol, 'tdMode': 'cash', 'side': 'sell',
            'ordType': 'oco', 'sz': fmt(qty), 'tpTriggerPx': fmt(tp),
            'tpOrdPx': '-1', 'slTriggerPx': fmt(sl), 'slOrdPx': '-1',
            'algoClOrdId': token}


def wait_filled(client, symbol, token, *, polls=4):
    for i in range(polls):
        result = client.request('GET', '/api/v5/trade/order',
                                params={'instId':symbol, 'clOrdId':token})
        if len(result) != 1:
            raise SpotHalt('entry status ambiguous; inspect OKX')
        row = result[0]
        state = row.get('state')
        if state == 'filled' and dec(row.get('accFillSz') or '0') > 0 and dec(row.get('avgPx') or '0') > 0:
            return dec(row['accFillSz']), dec(row['avgPx'])
        if state not in ('live','partially_filled'):
            raise SpotHalt('entry rejected/partial/canceled: inspect OKX')
        if i < polls-1:
            time.sleep(2)
    raise SpotHalt('entry not fully filled: manual OKX inspection required')


def verify_oco(client, symbol, token):
    rows = client.request('GET', '/api/v5/trade/orders-algo-pending',
                          params={'ordType': 'oco', 'instId': symbol})
    matches = [r for r in rows if r.get('algoClOrdId') == token and r.get('instId') == symbol]
    if len(matches) != 1 or matches[0].get('ordType') != 'oco':
        raise SpotHalt('OCO status not confirmed: manual OKX inspection required')
    return True


def execute(env, *, mode, scan_limit=25):
    if mode not in ('verify', 'live'):
        raise SpotHalt('invalid mode')
    client = OKXCash(env)
    no_derivatives_or_open_orders(client)
    funds = available(client, 'USDT')
    if funds < Decimal('5'):
        raise SpotHalt('too little available USDT')
    if mode == 'verify':
        return 'OKX SPOT VERIFIED (READ-ONLY): no orders sent'
    if not (env.get('OKX_EXECUTION_MODE') == 'live'
            and env.get('OKX_ENABLE_REAL_TRADING') == 'YES'
            and env.get('OKX_SPOT_LIVE_ARM') == 'I_AUTHORIZE_REAL_CASH_SPOT_LOSS'):
        raise SpotHalt('LIVE not armed: no orders sent')
    # Fresh public scan, then exchange revalidation before entry.
    report = scan(equity=min(funds, MAX_ORDER_USDT), max_pairs=scan_limit)
    if not report['watchlist']:
        return 'NO SPOT SIGNAL: no orders sent'
    candidate = report['watchlist'][0]
    symbol = candidate['symbol']
    inst = instrument(symbol)
    ask, bid = fresh_ticker(symbol)
    if (abs(ask / dec(candidate['last_closed_bar_close']) - 1) > Decimal('0.015')
            if 'last_closed_bar_close' in candidate else False):
        raise SpotHalt('price changed since closed-bar research')
    # The scanner is advisory; avoid an order when its market price changed sharply.
    quote_budget = min(funds * MAX_USDT_ALLOC, MAX_ORDER_USDT)
    plan = cash_plan(quote_budget, ask, inst)
    if not plan:
        return 'NO AFFORDABLE SPOT ORDER: no orders sent'
    base = symbol[:-5]
    if available(client, base) >= dec(inst['minSz']):
        raise SpotHalt('pre-existing base holding; will not mix with new OCO position')
    # Re-check final account state, no competing orders or derivatives.
    no_derivatives_or_open_orders(client)
    # Budget is capped and reduced for fees/slippage, and reserve remains in USDT.
    spend = floor_step(quote_budget * Decimal('0.98'), Decimal('0.01'))
    if spend <= 0 or spend / ask < dec(inst['minSz']):
        return 'NO AFFORDABLE SPOT ORDER: no orders sent'
    token = 'TMS' + uuid.uuid4().hex[:26]
    buy = entry_body(symbol, spend, token)
    client.request('POST', '/api/v5/trade/order', body=buy)
    # Never retry the POST: check actual order state by unique clOrdId.
    filled, avg = wait_filled(client, symbol, token)
    # Account may lag behind fills; read available balance a few times.
    qty = Decimal('0')
    for i in range(5):
        qty = min(available(client, base), filled)
        if floor_step(qty, dec(inst['lotSz'])) >= dec(inst['minSz']):
            break
        if i < 4:
            time.sleep(2)
    if floor_step(qty, dec(inst['lotSz'])) < dec(inst['minSz']):
        raise SpotHalt('URGENT: purchased amount cannot be protected; inspect OKX immediately')
    algo_token = 'TMPO' + uuid.uuid4().hex[:26]
    protection = protect_body(symbol, qty, avg, inst['tickSz'], inst['lotSz'], algo_token)
    # A failed/ambiguous POST must NOT trigger a duplicate automated order.
    client.request('POST', '/api/v5/trade/order-algo', body=protection)
    verify_oco(client, symbol, algo_token)
    return 'SPOT CASH ENTRY AND EXCHANGE OCO CONFIRMED; inspect OKX for current status'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['verify','live'], default='verify')
    parser.add_argument('--max-pairs', type=int, default=25)
    args = parser.parse_args(argv)
    if not 1 <= args.max_pairs <= 100:
        print('invalid pair count', file=sys.stderr)
        return 2
    try:
        message = execute(dict(os.environ), mode=args.mode, scan_limit=args.max_pairs)
        print(message)
        return 0
    except (SpotHalt, ValueError, ArithmeticError) as exc:
        # Do NOT print exchange payloads, API secrets or account balances.
        print('TITAN SPOT HALT: ' + str(exc), file=sys.stderr)
        return 2
    except Exception:
        print('TITAN SPOT HALT: Unexpected error; inspect OKX; never retry uncertain orders', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
