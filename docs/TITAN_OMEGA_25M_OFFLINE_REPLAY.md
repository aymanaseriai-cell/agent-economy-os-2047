# TITAN OMEGA 25M offline reproduction

Original full 432-trial real OKX historical evidence: GitHub Actions run
44064526902. Download its complete ZIP archive, checkout this research
branch, then run:

python -m trading.titan_omega_25m_replay --zip omega-singularity-25m-evidence.zip --out reports/offline_verification.json

This verifies six original true quote-volume OHLCV SHA256 snapshots,
six measured funding archive SHA256 hashes, and current instrument
spec snapshots. It then recomputes every train/dev/final simulation
with NO NETWORK and asserts exact match for 432 scores, all originally
chosen policy evidence, 6436 trade rows, capital curve, adjusted
exploratory statistical tests and financial verdict.

A reproducible negative result remains negative. No real exchange
orders, no physical quantum computer, no fabricated L2 depth.
