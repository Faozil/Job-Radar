"""Bundesagentur für Arbeit job search, as documented at https://github.com/bundesAPI/jobsuche-api

Not an official API: it is what the agency's own job search uses, so it could change.
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlencode

from ..http import FetchError, NotFoundError
from ..models import Job
from ..text import html_to_text, parse_datetime, unique
from .base import Getter, Source

logger = logging.getLogger(__name__)

API = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
HEADERS = {"X-API-Key": "jobboerse-jobsuche"}  # the public client id of the agency's website
JOB_PAGE = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}"
SEARCHES = ("DevOps", "Site Reliability", "Cloud Engineer", "Platform Engineer", "Kubernetes")
# The API ignores any other period and returns every ad it has.
PERIODS = (0, 1, 7, 14, 28)
PAGE_SIZE = 100
MAX_PAGES = 3


class BundesagenturFeed(Source):
    source = "bundesagentur"

    def __init__(
        self, searches: Sequence[str] = SEARCHES, days: int = 1, get: Getter | None = None
    ) -> None:
        super().__init__("de", "Bundesagentur für Arbeit", get)
        if days not in PERIODS:
            raise ValueError(f"Bundesagentur days must be one of {PERIODS}")
        self.searches = list(searches)
        self.days = days

    def url(self, search: str = SEARCHES[0], page: int = 1) -> str:
        query = {
            "was": search,
            "page": page,
            "size": PAGE_SIZE,
            "angebotsart": 1,  # jobs, not apprenticeships
            "veroeffentlichtseit": self.days,
            "pav": "false",  # no recruitment agencies
            "zeitarbeit": "false",  # no temp agencies
        }
        return f"{API}/pc/v6/jobs?{urlencode(query)}"

    def fetch(self) -> list[Job]:
        jobs: dict[str, Job] = {}
        for search in self.searches:
            for page in range(1, MAX_PAGES + 1):
                payload = self._get(self.url(search, page), headers=HEADERS) or {}
                items = payload.get("ergebnisliste") or []
                for job in self.parse(items):
                    jobs.setdefault(job.job_id, job)
                if len(items) < PAGE_SIZE:
                    break
        return list(jobs.values())

    def parse(self, payload: Any) -> list[Job]:
        jobs: list[Job] = []
        for item in payload or []:
            ref = item.get("referenznummer")
            title = str(item.get("stellenangebotsTitel") or "").strip()
            if not ref or not title:
                continue
            places = [place.get("adresse") or {} for place in item.get("stellenlokationen") or []]
            towns = [place.get("ort") for place in places]
            countries = [str(place.get("land") or "").title() for place in places]
            jobs.append(
                Job(
                    source=self.source,
                    board=self.board,
                    company=str(item.get("firma") or "Unknown company").strip(),
                    job_id=str(ref),
                    title=title,
                    url=str(item.get("externeURL") or JOB_PAGE.format(ref=ref)),
                    locations=unique([*towns, *countries]),
                    published_at=parse_datetime(item.get("datumErsteVeroeffentlichung")),
                )
            )
        return jobs

    def describe(self, jobs: list[Job]) -> list[Job]:
        return self.describe_each(jobs, self._read_ad)

    def _read_ad(self, job: Job) -> bool:
        ref = base64.b64encode(job.job_id.encode()).decode()
        try:
            detail = self._get(f"{API}/pc/v4/jobdetails/{ref}", headers=HEADERS) or {}
        except (FetchError, NotFoundError) as exc:
            logger.warning("no ad text for %s, trying again next run: %s", job.key, exc)
            return False
        job.description = html_to_text(detail.get("stellenangebotsBeschreibung"))
        return True
