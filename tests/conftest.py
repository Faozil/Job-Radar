from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from jobradar.config import AppConfig, load_config
from jobradar.models import Job

REPO_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 9, 8, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def app_config() -> AppConfig:
    return load_config(REPO_ROOT / "config" / "job-radar.toml")


def make_job(**overrides: object) -> Job:
    values: dict[str, object] = {
        "source": "greenhouse",
        "board": "acme",
        "company": "Acme",
        "job_id": "1",
        "title": "DevOps Engineer",
        "url": "https://example.com/jobs/1",
        "locations": ["Berlin, Germany"],
        "remote": None,
        "description": "We build things.",
        "published_at": NOW,
    }
    values.update(overrides)
    return Job(**values)  # type: ignore[arg-type]
