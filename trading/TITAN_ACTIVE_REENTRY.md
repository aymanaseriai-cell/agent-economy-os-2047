# TITAN Omega guarded active re-entry

- After a confirmed full close, the exchange state monitor polls a 30-second
  cooldown at 5-second intervals, instead of 10 seconds.
- The original exchange-confirmed 30-second minimum is unchanged.
- Startup scans immediately; no qualifying signal means no order. Not a
  guaranteed position at startup or exactly 30 seconds after exiting.
- Existing six-agent council, seven filters, Omega vetoes, stop protection,
  margin and portfolio caps, and owner emergency stop remain unchanged.
- No private order retries and no automatic override of a missing signal.
- Requires prior independent consent to live/repeated orders.
- Update does not enable the disabled real-money workflow.
- Test: python -m unittest discover -s tests -p test_okx_five_second_worker.py -v
