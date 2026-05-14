.PHONY: setup dev test demo health

PYTHON := .venv/bin/python3
PIP := .venv/bin/pip
CLI := $(PYTHON) scripts/negotiate_cli.py

setup:
	python3 -m venv .venv
	$(PIP) install -r requirements.txt

dev:
	$(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

test:
	APP_MASTER_KEY=test-master-key $(PYTHON) -m pytest -q

health:
	$(CLI) health

demo:
	$(CLI) demo-cycle
