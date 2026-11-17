# TITAN 300-second post-exit re-evaluation

Research branch only. A new entry is eligible for evaluation no earlier than 300 seconds after an exchange-confirmed fully closed USDT swap position, including liquidations and ADL closures.
Exchange position history is the durable clock. A runner restart cannot bypass this lock. Polling every five seconds is read-only; it does not shorten the cooldown. After the lock expires, a fresh valid signal is still required; no forced trade.

This ChatGPT conversation cannot continuously supervise or decide trades 24/7. Such a system needs a persistent host and an explicitly configured model API and exchange integration. GitHub Actions alone does not guarantee uninterrupted execution or continuous position protection.

Trading remains disarmed. Do not use maximum leverage or full-margin allocation to chase a 4.14 USDT to 7 million USD target; no leveraged strategy can ensure zero liquidation risk. No order endpoint is activated in this branch.

Unit tests: python -m unittest discover -s tests -v