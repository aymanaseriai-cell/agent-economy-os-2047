#!/usr/bin/env python3
"""Authenticated READ-ONLY OKX state monitor for explicitly armed chained sessions.

Reports only a coarse non-sensitive state. Never creates, modifies, cancels or
closes an order. If a position is unprotected, pending orders are ambiguous,
or cooldown history is inaccessible, stop; never interpret uncertainty as flat.
"""
from __future__ import annotations

import os
import sys

from trading.okx_live_executor import (
    OKX, ExecutionBlocked, ReentryCooldownActive, check_mode, dec, enforce_exit_cooldown,
)

STATES = frozenset(("FLAT_ELIGIBLE", "POSITION_OPEN_PROTECTED", "COOLDOWN_ACTIVE"))


def inspect_account_state(client) -> str:
    """One conservative snapshot. A second exchange preflight still gates entry."""
    config=client.request('GET','/api/v5/account/config')
    if len(config)!=1 or config[0].get('posMode')!='net_mode':
        raise ExecutionBlocked('Monitor: expected OKX net_mode')
    rows=client.request('GET','/api/v5/account/positions',params={'instType':'SWAP'})
    active=[p for p in rows if dec(p.get('pos','0'))!=0]
    if len(active)>1:
        raise ExecutionBlocked('Monitor: multiple active SWAP positions; manual review')
    pending=client.request('GET','/api/v5/trade/orders-pending',params={'instType':'SWAP'})
    if pending:
        raise ExecutionBlocked('Monitor: unverified pending SWAP orders; manual review')
    algos=[]
    for typ in ('conditional','oco','trigger','move_order_stop'):
        rows=client.request('GET','/api/v5/trade/orders-algo-pending',params={'ordType':typ})
        algos.extend(row for row in rows if str(row.get('instId','')).endswith('-SWAP'))
    if active:
        symbol=active[0].get('instId','')
        if not symbol.endswith('-USDT-SWAP'):
            raise ExecutionBlocked('Monitor: active position is not a USDT perpetual')
        if any(order.get('instId')!=symbol for order in algos):
            raise ExecutionBlocked('Monitor: unrelated SWAP algos detected')
        if not any(a.get('instId')==symbol and a.get('slTriggerPx') and a.get('tpTriggerPx')
                   for a in algos):
            raise ExecutionBlocked('Monitor: attached TP/SL no longer verifiable; inspect OKX')
        return 'POSITION_OPEN_PROTECTED'
    if algos:
        raise ExecutionBlocked('Monitor: orphaned SWAP algo orders; inspect OKX')
    try:
        enforce_exit_cooldown(client)
    except ReentryCooldownActive:
        return 'COOLDOWN_ACTIVE'
    return 'FLAT_ELIGIBLE'


def main() -> int:
    try:
        env=dict(os.environ)
        mode=env.get('OKX_EXECUTION_MODE','dry_run')
        if env.get('OKX_AUTOREENTRY_ENABLED')!='YES':
            raise ExecutionBlocked('Monitor is not separately armed')
        if mode=='dry_run':
            print('OKX MONITOR RESULT: FLAT_ELIGIBLE',flush=True)
            return 0
        check_mode(mode,env)
        state=inspect_account_state(OKX(env))
        print('OKX MONITOR RESULT: '+state,flush=True)
        return 0
    except ExecutionBlocked as exc:
        print('OKX MONITOR BLOCKED: '+str(exc),file=sys.stderr,flush=True)
        return 2
    except Exception:
        print('OKX MONITOR ERROR: account state unknown; manual review required',
              file=sys.stderr,flush=True)
        return 3


if __name__=='__main__':
    raise SystemExit(main())
