.PHONY: setup dev test demo health package package-check publish-test

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

package:
	$(PIP) install build
	$(PYTHON) -m build

package-check:
	$(PIP) install twine
	$(PYTHON) -m twine check dist/*

publish-test:
	$(PIP) install twine
	$(PYTHON) -m twine upload --repository testpypi dist/*
