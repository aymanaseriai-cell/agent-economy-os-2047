# Retry on NO_CONSENSUS

GitHub Actions now tries up to **8 full public market scans** per scheduled
or manual run. If the unchanged guarded OKX executor returns NO_CONSENSUS
after a completed full scan, the runner pauses **5 seconds** before beginning
another full scan. A retry session ends at 245 seconds or 8 scans.

Each 12-market scan usually takes 20 seconds or longer, so the actual
start-to-start interval is full scan duration PLUS 5 seconds, not precisely
5 seconds. GitHub Actions scheduling remains every five minutes and may be
delayed. A genuine round-the-clock 5-second scan needs persistent hosting
and a faster scanning algorithm.

Any scan error, executor error, AI veto, exchange risk veto, order, trade
signal, or unexpected response terminates all retries. The existing 10-minute
post-exit cooldown, 10x leverage, one-position rule and TP/SL controls are
unchanged. No uncertain order execution is retried.
