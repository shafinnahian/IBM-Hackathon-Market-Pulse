#!/usr/bin/env bash
# One-command setup: install deps and create DB if missing.
# Run: ./setup.sh   (or: bash setup.sh)
set -e
pip install -e .
python -m market_pulse.scripts.ensure_db
