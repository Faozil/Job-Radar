from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from .models import Job

DEFAULT_TTL_DAYS = 120


class SeenStore(Protocol):
    def seen_keys(self, keys: Iterable[str]) -> set[str]: ...

    def mark_seen(self, jobs: Sequence[Job], now: datetime) -> None: ...


class MemoryStore:
    """In-memory store for tests and dry runs."""

    def __init__(self) -> None:
        self.items: dict[str, str] = {}

    def seen_keys(self, keys: Iterable[str]) -> set[str]:
        return {key for key in keys if key in self.items}

    def mark_seen(self, jobs: Sequence[Job], now: datetime) -> None:
        for job in jobs:
            self.items.setdefault(job.key, now.isoformat(timespec="seconds"))


class FileStore:
    """JSON file store, used when running outside AWS (locally or on GitHub Actions)."""

    def __init__(self, path: str | Path, ttl_days: int = DEFAULT_TTL_DAYS) -> None:
        self.path = Path(path)
        self.ttl_days = ttl_days

    def _load(self) -> dict[str, str]:
        if not self.path.is_file():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        seen = data.get("seen") if isinstance(data, dict) else None
        return dict(seen) if isinstance(seen, dict) else {}

    def seen_keys(self, keys: Iterable[str]) -> set[str]:
        stored = self._load()
        return {key for key in keys if key in stored}

    def mark_seen(self, jobs: Sequence[Job], now: datetime) -> None:
        stored = self._load()
        cutoff = now - timedelta(days=self.ttl_days)
        stored = {key: when for key, when in stored.items() if _parse(when) >= cutoff}
        for job in jobs:
            stored.setdefault(job.key, now.isoformat(timespec="seconds"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"version": 1, "seen": stored}, indent=1), encoding="utf-8")
        os.replace(temporary, self.path)


class DynamoStore:
    """Items expire through the table's TTL."""

    def __init__(
        self,
        table: str,
        client: Any = None,
        ttl_days: int = DEFAULT_TTL_DAYS,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 6,
    ) -> None:
        self.table = table
        self.ttl_days = ttl_days
        self._client = client
        self._sleep = sleep
        self._max_attempts = max_attempts

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3  # available in the Lambda runtime; not needed for local runs

            self._client = boto3.client("dynamodb")
        return self._client

    def seen_keys(self, keys: Iterable[str]) -> set[str]:
        found: set[str] = set()
        unique_keys = list(dict.fromkeys(keys))
        for chunk in _chunks(unique_keys, 100):  # BatchGetItem limit
            pending: dict[str, Any] = {
                self.table: {
                    "Keys": [{"job_key": {"S": key}} for key in chunk],
                    "ProjectionExpression": "job_key",
                }
            }
            for attempt in range(self._max_attempts):
                response = self.client.batch_get_item(RequestItems=pending)
                for item in response.get("Responses", {}).get(self.table, []):
                    found.add(item["job_key"]["S"])
                pending = response.get("UnprocessedKeys") or {}
                if not pending:
                    break
                self._sleep(0.25 * 2**attempt)
            else:
                raise RuntimeError("DynamoDB kept returning unprocessed keys")
        return found

    def mark_seen(self, jobs: Sequence[Job], now: datetime) -> None:
        expires_at = int(now.timestamp()) + self.ttl_days * 86_400
        requests = [
            {
                "PutRequest": {
                    "Item": {
                        "job_key": {"S": job.key},
                        "title": {"S": job.title[:300]},
                        "company": {"S": job.company[:200]},
                        "url": {"S": job.url[:1000]},
                        "first_seen": {"S": now.isoformat(timespec="seconds")},
                        "expires_at": {"N": str(expires_at)},
                    }
                }
            }
            for job in {job.key: job for job in jobs}.values()
        ]
        for chunk in _chunks(requests, 25):  # BatchWriteItem limit
            pending: dict[str, Any] = {self.table: chunk}
            for attempt in range(self._max_attempts):
                response = self.client.batch_write_item(RequestItems=pending)
                pending = response.get("UnprocessedItems") or {}
                if not pending:
                    break
                self._sleep(0.25 * 2**attempt)
            else:
                raise RuntimeError("DynamoDB kept returning unprocessed items")


def _chunks(items: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _parse(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=UTC)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
