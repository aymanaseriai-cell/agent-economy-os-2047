# Frozen public OKX edge lab

Research only. No API keys, private endpoints, order placement, or account access.
This lab intentionally does not imitate missing historical L2 and NVIDIA AI data.
It tests two predetermined, simple OHLC strategy prototypes on complete historical
OKX USDT perpetual candles, with chronological train/holdout split and conservative costs.

## Quick start

    python -m unittest discover -s tests -p test_edge_lab.py -v
    python -m trading.edge_lab --days 60 --offline-dir reports --out reports/replay.json

Run public-network fresh data with:

    python -m trading.edge_lab --days 60 --out reports/new_run.json

Frozen data: reports/*-USDT-SWAP.candles.json.gz, plus SHA256 manifest.
Main analysis: reports/okx_edge_lab_20261108.md.
GitHub workflow okx-edge-lab-audit.yml is manual and public-data-only.

The actual OKX live-execution workflow is intentionally disabled.
