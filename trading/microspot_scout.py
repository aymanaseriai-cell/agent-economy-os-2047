"""TITAN MicroSpot: public, READ-ONLY cash-spot momentum research for small wallets.

No API keys, no private OKX API requests, no real orders, no margin or leverage.
Watchlist signals have no proven predictive value; NOT an investment forecast.
"""
from __future__ import annotations
import argparse
import json
import math
import sys
import time
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from pathlib import Path
from statistics import mean
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = 'https://www.okx.com'
FEE_SIDE = Decimal('0.001')       # Illustrative 0.1% each side, NOT an account fee quote.
SLIPPAGE_SIDE = Decimal('0.0015')  # Illustrative 0.15% each side.
MAX_SPREAD_PCT = Decimal('0.25')
MIN_QUOTE_VOL = Decimal('20000000')
BAR = '5m'


def dec(value):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('Invalid numeric field') from exc
    if not n.is_finite():
        raise ValueError('Nonfinite numeric field')
    return n


def public_get(path, params=None, *, timeout=12):
    allowed = {'/api/v5/market/tickers', '/api/v5/public/instruments',
               '/api/v5/market/candles', '/api/v5/market/ticker'}
    if path not in allowed:
        raise ValueError('Public endpoints only')
    url = BASE + path + ('?' + urlencode(params) if params else '')
    request = Request(url, headers={'User-Agent': 'TITAN-MicroSpot-Research/1.0'})
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if (not isinstance(payload, dict) or str(payload.get('code')) != '0'
            or not isinstance(payload.get('data'), list)):
        raise RuntimeError('Public OKX data unavailable')
    return payload['data']


def floor_step(amount, step):
    amount, step = dec(amount), dec(step)
    if amount <= 0 or step <= 0:
        raise ValueError('Invalid quantity/lot step')
    return (amount / step).to_integral_value(rounding=ROUND_FLOOR) * step


def cash_plan(equity, ask, inst, *, fee_side=FEE_SIDE):
    """Calculate cash-only feasible paper size; NEVER place an order."""
    equity, ask, fee_side = dec(equity), dec(ask), dec(fee_side)
    if equity <= 0 or ask <= 0 or fee_side < 0:
        return None
    if not isinstance(inst, dict) or inst.get('state') != 'live':
        return None
    if not inst.get('instId', '').endswith('-USDT'):
        return None
    lot, minimum = dec(inst.get('lotSz', '0')), dec(inst.get('minSz', '0'))
    if lot <= 0 or minimum <= 0:
        return None
    # Preserve a little cash and include approximate entry fee in paper cost.
    budget = equity * Decimal('0.99')
    qty = floor_step(budget / (ask * (1 + fee_side)), lot)
    if qty < minimum:
        return None
    cost = qty * ask * (1 + fee_side)
    if cost > budget:
        return None
    return {'paper_quantity_base': str(qty),
            'paper_entry_cost_usdt': str(cost),
            'unallocated_cash_usdt': str(equity - cost),
            'tdMode': 'cash', 'leverage': 1, 'order_placed': False}


def closed_bars(raw):
    """OKX returns newest first. Use only confirm=1; never use a forming candle."""
    bars = []
    for row in raw:
        if not isinstance(row, list) or len(row) < 9 or str(row[8]) != '1':
            continue
        try:
            bar = {'ts': int(row[0]), 'open': float(row[1]),
                   'high': float(row[2]), 'low': float(row[3]),
                   'close': float(row[4]), 'quote_vol': float(row[7])}
        except (ValueError, TypeError):
            continue
        if (not all(math.isfinite(bar[k]) for k in
                    ('open', 'high', 'low', 'close', 'quote_vol'))
                or min(bar['open'], bar['high'], bar['low'], bar['close']) <= 0
                or bar['quote_vol'] < 0 or bar['high'] < bar['low']):
            continue
        bars.append(bar)
    bars.sort(key=lambda x: x['ts'])
    if len({x['ts'] for x in bars}) != len(bars):
        return []
    return bars


def signal(bars, ask, bid, *, fee_side=FEE_SIDE,
           slippage_side=SLIPPAGE_SIDE, now_ms=None):
    """Closed-candle-only breakout. Labels are research, NOT profit predictions."""
    if len(bars) < 60:
        return None
    ask, bid = dec(ask), dec(bid)
    if bid <= 0 or ask <= bid:
        return None
    spread = (ask - bid) / ask * 100
    if spread > MAX_SPREAD_PCT:
        return None
    c = bars[-1]
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    # A completed 5m candle older than 15 minutes is not live enough to trade.
    if c['ts'] > now_ms or now_ms - c['ts'] > 15 * 60 * 1000:
        return None
    prev = bars[-21:-1]
    prior_high = max(x['high'] for x in prev)
    if not (c['close'] > prior_high):
        return None
    avg_vol = mean(x['quote_vol'] for x in prev)
    if avg_vol <= 0:
        return None
    ratio = c['quote_vol'] / avg_vol
    if ratio < 1.6:
        return None
    closes = [x['close'] for x in bars]
    sma20, sma50 = mean(closes[-20:]), mean(closes[-50:])
    if not (c['close'] > sma20 > sma50):
        return None
    if abs(ask / dec(c['close']) - 1) > Decimal('0.015'):
        return None
    tr = [max(bars[i]['high'] - bars[i]['low'],
              abs(bars[i]['high'] - bars[i-1]['close']),
              abs(bars[i]['low'] - bars[i-1]['close']))
          for i in range(len(bars)-14, len(bars))]
    atr_frac = mean(tr) / c['close']
    stop_frac = min(.035, max(.012, atr_frac * 1.5))
    costs_pct = (dec(fee_side) + dec(slippage_side)) * 200 + spread
    # Illustrative R multiple, NOT the expected direction or win probability.
    hypothetical_target_pct = Decimal(str(stop_frac * 180)) + costs_pct
    score = round(min(5., ratio) + min(2., (c['close'] / sma50 - 1) * 100), 3)
    return {'signal': 'BUY_WATCH_ONLY', 'score': score,
            'relative_volume': round(ratio, 2),
            'spread_pct': round(float(spread), 4),
            'modeled_roundtrip_cost_pct': round(float(costs_pct), 4),
            'illustrative_stop_distance_pct': round(stop_frac * 100, 3),
            'hypothetical_target_move_pct': round(float(hypothetical_target_pct), 3),
            'last_closed_bar_ts_ms': c['ts'], 'last_closed_bar_close': c['close']}


def scan(*, equity=Decimal('9'), max_pairs=25, min_quote_vol=MIN_QUOTE_VOL):
    equity = dec(equity)
    if equity <= 0 or max_pairs < 1 or dec(min_quote_vol) < 0:
        raise ValueError('Invalid scanner parameters')
    tickers = public_get('/api/v5/market/tickers', {'instType': 'SPOT'})
    insts = public_get('/api/v5/public/instruments', {'instType': 'SPOT'})
    by_id = {x.get('instId'): x for x in insts if isinstance(x, dict)}
    eligible = []
    for tick in tickers:
        if not isinstance(tick, dict):
            continue
        symbol = tick.get('instId', '')
        if not symbol.endswith('-USDT') or symbol not in by_id:
            continue
        try:
            vol = dec(tick.get('volCcy24h', '0'))  # Quote-CCY 24h SPOT volume.
            ask, bid = dec(tick.get('askPx', '0')), dec(tick.get('bidPx', '0'))
            if vol < dec(min_quote_vol) or bid <= 0 or ask <= bid:
                continue
            plan = cash_plan(equity, ask, by_id[symbol])
            if not plan or (ask - bid) / ask * 100 > MAX_SPREAD_PCT:
                continue
        except (ValueError, InvalidOperation):
            continue
        eligible.append((vol, symbol, ask, bid, plan))
    eligible.sort(key=lambda row: row[0], reverse=True)
    watchlist, feed_errors = [], 0
    for _, symbol, ask, bid, plan in eligible[:max_pairs]:
        try:
            bars = closed_bars(public_get('/api/v5/market/candles',
                             {'instId': symbol, 'bar': BAR, 'limit': '100'}))
            candidate = signal(bars, ask, bid)
            if candidate:
                watchlist.append({'symbol': symbol, **candidate,
                                  'cash_feasibility': plan})
        except (RuntimeError, OSError, TimeoutError, ValueError):
            feed_errors += 1
    watchlist.sort(key=lambda row: row['score'], reverse=True)
    return {'program': 'TITAN MicroSpot research-only',
            'mode': 'PUBLIC_READ_ONLY', 'orders_sent': 0,
            'private_api_calls': 0, 'margin': False,
            'input_equity_usdt_unverified': str(equity),
            'screened_affordable_pairs': len(eligible),
            'candle_pairs_checked': min(len(eligible), max_pairs),
            'candle_data_errors': feed_errors, 'watchlist': watchlist[:5],
            'status': 'WATCHLIST_ONLY' if watchlist else 'NO_QUALIFIED_SIGNAL',
            'caveat': 'No validated edge and no guaranteed route to 90 USDT.'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--equity-usdt', type=Decimal, default=Decimal('9'))
    p.add_argument('--max-pairs', type=int, default=25)
    p.add_argument('--min-quote-vol', type=Decimal, default=MIN_QUOTE_VOL)
    p.add_argument('--output', default='reports/microspot_scout.json')
    args = p.parse_args(argv)
    try:
        report = scan(equity=args.equity_usdt, max_pairs=args.max_pairs,
                      min_quote_vol=args.min_quote_vol)
    except (ValueError, RuntimeError, OSError) as exc:
        print('MicroSpot public feed unavailable: ' + type(exc).__name__, file=sys.stderr)
        return 1
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in
                      ('mode', 'orders_sent', 'screened_affordable_pairs',
                       'candle_pairs_checked', 'candle_data_errors', 'status')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
