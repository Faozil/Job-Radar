from __future__ import annotations

import json
import logging
import os
from typing import Any

from . import metrics
from .config import AppConfig, load_config
from .notify import TelegramNotifier
from .pipeline import run
from .sources import build_sources
from .store import DynamoStore

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

PLACEHOLDER_PREFIX = "set-me"  # what Terraform writes into the SSM parameters

# Kept between warm invocations, so config and secrets are read once per container.
_cache: dict[str, Any] = {}


class SetupError(RuntimeError):
    """Configuration is incomplete, e.g. the Telegram secrets were never set."""


def _ssm_value(name: str) -> str:
    if "ssm" not in _cache:
        import boto3  # included in the Lambda Python runtime

        _cache["ssm"] = boto3.client("ssm")
    response = _cache["ssm"].get_parameter(Name=name, WithDecryption=True)
    value = str(response["Parameter"]["Value"]).strip()
    if not value or value.startswith(PLACEHOLDER_PREFIX):
        raise SetupError(f"SSM parameter {name} still holds the placeholder; set the real value")
    return value


def _config() -> AppConfig:
    if "config" not in _cache:
        _cache["config"] = load_config()
    return _cache["config"]


def _notifier() -> TelegramNotifier:
    if "notifier" not in _cache:
        _cache["notifier"] = TelegramNotifier(
            token=_ssm_value(os.environ["TELEGRAM_TOKEN_PARAM"]),
            chat_id=_ssm_value(os.environ["TELEGRAM_CHAT_ID_PARAM"]),
        )
    return _cache["notifier"]


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, object]:
    config = _config()
    result = run(
        build_sources(config),
        config.filters,
        DynamoStore(os.environ["SEEN_TABLE"]),
        _notifier(),
        max_per_run=config.max_per_run,
    )
    metrics.emit(result, os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "job-radar"))
    summary = result.as_dict()
    # print, not logging: Logs Insights parses a bare JSON line into fields.
    print(json.dumps({"event": "run_complete", **summary}))
    return summary
