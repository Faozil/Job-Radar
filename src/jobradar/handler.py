from __future__ import annotations

import json
import logging
import os
from typing import Any

from . import metrics
from .config import AppConfig, load_config
from .notify import EmailNotifier
from .pipeline import run
from .sources import build_sources
from .store import DynamoStore

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Kept between warm invocations, so config and secrets are read once per container.
_cache: dict[str, Any] = {}


def _ssm_value(name: str) -> str:
    if "ssm" not in _cache:
        import boto3  # included in the Lambda Python runtime

        _cache["ssm"] = boto3.client("ssm")
    response = _cache["ssm"].get_parameter(Name=name, WithDecryption=True)
    return str(response["Parameter"]["Value"]).strip()


def _config() -> AppConfig:
    if "config" not in _cache:
        _cache["config"] = load_config()
    return _cache["config"]


def _notifier() -> EmailNotifier:
    if "notifier" not in _cache:
        _cache["notifier"] = EmailNotifier(
            address=_ssm_value(os.environ["EMAIL_ADDRESS_PARAM"]),
            password=_ssm_value(os.environ["EMAIL_PASSWORD_PARAM"]),
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
