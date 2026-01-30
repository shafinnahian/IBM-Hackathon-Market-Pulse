# One-command setup: install deps and create DB if missing.
# Run: make setup
.PHONY: setup
setup:
	pip install -e .
	python -m market_pulse.scripts.ensure_db
