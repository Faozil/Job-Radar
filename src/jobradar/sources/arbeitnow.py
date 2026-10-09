"""Arbeitnow job board API (mostly Germany): https://www.arbeitnow.com/blog/job-board-api"""

from __future__ import annotations

from typing import Any

from ..models import Job
from ..text import html_to_text, parse_datetime, unique
from .base import Getter, Source


class ArbeitnowFeed(Source):
    source = "arbeitnow"

    def __init__(self, pages: int = 3, get: Getter | None = None) -> None:
        super().__init__("feed", "Arbeitnow", get)
        self.pages = max(1, pages)

    def url(self, page: int = 1) -> str:
        return f"https://www.arbeitnow.com/api/job-board-api?page={page}"

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for page in range(1, self.pages + 1):
            payload = self._get(self.url(page)) or {}
            batch = self.parse(payload)
            if not batch:
                break
            jobs.extend(batch)
            links = payload.get("links")
            if isinstance(links, dict) and not links.get("next"):
                break
        return jobs

    def parse(self, payload: Any) -> list[Job]:
        jobs: list[Job] = []
        for item in (payload or {}).get("data") or []:
            title = str(item.get("title") or "").strip()
            slug = item.get("slug")
            if not title or not slug:
                continue
            remote = item.get("remote")
            jobs.append(
                Job(
                    source=self.source,
                    board=self.board,
                    company=str(item.get("company_name") or "Unknown company").strip(),
                    job_id=str(slug),
                    title=title,
                    url=str(item.get("url") or ""),
                    locations=unique([item.get("location")]),
                    remote=remote if isinstance(remote, bool) else None,
                    description=html_to_text(item.get("description")),
                    published_at=parse_datetime(item.get("created_at")),
                )
            )
        return jobs
