PYTHON ?= python3
export PYTHONPATH := src

.PHONY: install test lint format dry-run check-boards chat-id scan

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

# Find your Telegram chat id. Run `read -rs TELEGRAM_BOT_TOKEN && export TELEGRAM_BOT_TOKEN` first.
chat-id:
	$(PYTHON) -m jobradar telegram-chat-id

scan:
	checkov -d infra --framework terraform --compact --quiet --skip-download
