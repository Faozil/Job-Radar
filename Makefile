PYTHON ?= python3
export PYTHONPATH := src

.PHONY: install test lint format dry-run check-boards test-email scan

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
	terraform fmt -check -recursive infra

format:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .
	terraform fmt -recursive infra

dry-run:
	$(PYTHON) -m jobradar run --dry-run --all

check-boards:
	$(PYTHON) -m jobradar check-boards

# Needs EMAIL_ADDRESS and EMAIL_APP_PASSWORD exported (see the README).
test-email:
	$(PYTHON) -m jobradar test-email

scan:
	checkov -d infra --framework terraform --compact --quiet --skip-download
