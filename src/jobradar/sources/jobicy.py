"""Jobicy remote jobs API: https://jobicy.com/api/v2/remote-jobs

Jobicy asks API users to check at most once an hour and to link back to each job.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlencode

from ..models import Job
from ..text import html_to_text, parse_datetime, unique
from .base import Getter, Source

API = "https://jobicy.com/api/v2/remote-jobs"
TAGS = ("devops", "sre", "kubernetes", "cloud")


class JobicyFeed(Source):
    source = "jobicy"

    def __init__(self, tags: Sequence[str] = TAGS, get: Getter | None = None) -> None:
        super().__init__("remote", "Jobicy", get)
        self.tags = list(tags)

    def url(self, tag: str = TAGS[0]) -> str:
        return f"{API}?{urlencode({'count': 100, 'tag': tag})}"

    def fetch(self) -> list[Job]:
        jobs: dict[str, Job] = {}
        for tag in self.tags:
            for job in self.parse(self._get(self.url(tag))):
                jobs.setdefault(job.job_id, job)
        return list(jobs.values())

    def parse(self, payload: Any) -> list[Job]:
        jobs: list[Job] = []
        for item in (payload or {}).get("jobs") or []:
            title = html.unescape(str(item.get("jobTitle") or "")).strip()
            if not title or item.get("id") is None:
                continue
            company = html.unescape(str(item.get("companyName") or "Unknown company")).strip()
            jobs.append(
                Job(
                    source=self.source,
                    board=self.board,
                    company=company,
                    job_id=str(item["id"]),
                    title=title,
                    url=str(item.get("url") or ""),
                    locations=unique(str(item.get("jobGeo") or "").split(",")),
                    remote=True,
                    description=html_to_text(item.get("jobDescription")),
                    published_at=parse_datetime(item.get("pubDate")),
                )
            )
        return jobs
