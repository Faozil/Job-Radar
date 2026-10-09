"""CloudWatch metrics through the Embedded Metric Format: a log line, no PutMetricData calls."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from .pipeline import RunResult

NAMESPACE = "JobRadar"


def emf_record(result: RunResult, function_name: str, now_ms: int | None = None) -> dict[str, Any]:
    values = {
        "JobsFetched": result.fetched,
        "Matches": result.matched,
        "NewJobs": result.new,
        "BoardErrors": len(result.failed),
    }
    return {
        "_aws": {
            "Timestamp": now_ms if now_ms is not None else int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": NAMESPACE,
                    "Dimensions": [["Function"]],
                    "Metrics": [{"Name": name, "Unit": "Count"} for name in values],
                }
            ],
        },
        "Function": function_name,
        **values,
    }


def emit(result: RunResult, function_name: str, write: Callable[[str], Any] = print) -> None:
    write(json.dumps(emf_record(result, function_name)))
