"""SmartRecruiters Posting API: https://developers.smartrecruiters.com/docs/posting-api"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote, urlencode

from ..http import FetchError, NotFoundError
from ..models import Job
from ..text import html_to_text, parse_datetime, unique
from .base import Source

logger = logging.getLogger(__name__)

API = "https://api.smartrecruiters.com/v1/companies/{company}/postings"
# The search covers the whole ad, so a few specific words keep big employers' results small.
SEARCHES = ("devops", "kubernetes", "terraform")
SECTIONS = ("jobDescription", "qualifications", "additionalInformation", "companyDescription")
PAGE_SIZE = 100
MAX_PAGES = 3


class SmartRecruitersBoard(Source):
    source = "smartrecruiters"

    @property
    def postings(self) -> str:
        return API.format(company=quote(self.board))

    def url(self, search: str = SEARCHES[0], offset: int = 0) -> str:
        return f"{self.postings}?{urlencode({'q': search, 'limit': PAGE_SIZE, 'offset': offset})}"

    def fetch(self) -> list[Job]:
        jobs: dict[str, Job] = {}
        for search in SEARCHES:
            for page in range(MAX_PAGES):
                items = (self._get(self.url(search, page * PAGE_SIZE)) or {}).get("content") or []
                for job in self.parse(items):
                    jobs.setdefault(job.job_id, job)
                if len(items) < PAGE_SIZE:
                    break
        return list(jobs.values())

    def parse(self, payload: Any) -> list[Job]:
        jobs: list[Job] = []
        for item in payload or []:
            title = str(item.get("name") or "").strip()
            if not title or not item.get("id"):
                continue
            place = item.get("location") or {}
            remote = bool(place.get("remote"))
            jobs.append(
                Job(
                    source=self.source,
                    board=self.board,
                    company=self.name,
                    job_id=str(item["id"]),
                    title=title,
                    url=f"https://jobs.smartrecruiters.com/{quote(self.board)}/{quote(str(item['id']))}",
                    locations=unique([place.get("fullLocation"), "Remote" if remote else None]),
                    remote=True if remote else None,
                    published_at=parse_datetime(item.get("releasedDate")),
                )
            )
        return jobs

    def describe(self, jobs: list[Job]) -> list[Job]:
        return self.describe_each(jobs, self._read_ad)

    def _read_ad(self, job: Job) -> bool:
        try:
            detail = self._get(f"{self.postings}/{quote(job.job_id)}") or {}
        except (FetchError, NotFoundError) as exc:
            logger.warning("no ad text for %s, trying again next run: %s", job.key, exc)
            return False
        sections = (detail.get("jobAd") or {}).get("sections") or {}
        texts = (html_to_text((sections.get(name) or {}).get("text")) for name in SECTIONS)
        job.description = "\n".join(text for text in texts if text)
        job.url = str(detail.get("postingUrl") or job.url)
        return True
