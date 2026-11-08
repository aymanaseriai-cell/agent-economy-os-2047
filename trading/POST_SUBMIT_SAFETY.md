# Post-submit uncertainty recovery (disabled trading bot)

The trade executor is hardened for already submitted entries. If it cannot
read the entry order's status, if repeated status polls do not confirm an order,
or if attached TP/SL order status is unreadable, it attempts a best-effort
reduceOnly market close of any current position on that instrument.

It never retries the original entry order in these situations. An uncertain
status always raises an URGENT exception requiring manual OKX inspection
rather than pretending a flat account or an established stop. A failed close,
unknown fill, delayed or stale exchange positions feed, slippage, API outage,
and liquidations remain possible. The only reliable final confirmation of
risk exposure is the exchange account itself.

This patch does NOT change signal selection, margin sizing, leverage, or the
status of the disabled GitHub Actions trading workflow. The user's stop request
takes priority. OKX_ENABLE_REAL_TRADING=NO and OKX_EXECUTION_MODE=dry_run
must remain in effect until a separate explicit restart request.

Tests simulate order-status reads failing, missing confirmations, unreadable
protective orders, emergency-close failures, and verified protective orders.
No live order is sent by the tests.
