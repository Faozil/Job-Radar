"""We Work Remotely's public RSS feed of DevOps and sysadmin jobs."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable
from typing import Any

from ..http import fetch as fetch_url
from ..models import Job
from ..text import html_to_text, parse_datetime, unique
from .base import Source

FEED = "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss"


class WeWorkRemotelyFeed(Source):
    source = "weworkremotely"

    def __init__(self, fetch: Callable[[str], bytes] | None = None) -> None:
        super().__init__("devops", "We Work Remotely")
        self._download = fetch or fetch_url

    def url(self) -> str:
        return FEED

    def fetch(self) -> list[Job]:
        return self.parse(self._download(self.url()))

    def parse(self, payload: Any) -> list[Job]:
        # The standard library parser is safe enough here: expat 2.4+ caps entity expansion and the
        # feed comes from one fixed https host.
        root = ET.fromstring(payload)  # noqa: S314
        jobs: list[Job] = []
        for item in root.iter("item"):
            company, _, title = (item.findtext("title") or "").partition(": ")
            link = (item.findtext("link") or "").strip()
            if not title.strip() or not link:
                continue
            jobs.append(
                Job(
                    source=self.source,
                    board=self.board,
                    company=company.strip(),
                    job_id=link.rstrip("/").rsplit("/", 1)[-1],
                    title=title.strip(),
                    url=link,
                    locations=unique([item.findtext("region")]),
                    remote=True,
                    description=html_to_text(item.findtext("description")),
                    published_at=parse_datetime(item.findtext("pubDate")),
                )
            )
        return jobs
