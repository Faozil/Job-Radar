"""Ashby public job posting API: https://developers.ashbyhq.com/docs/public-job-posting-api"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..models import Job
from ..text import html_to_text, parse_datetime, unique
from .base import Source


class AshbyBoard(Source):
    source = "ashby"

    def url(self) -> str:
        return f"https://api.ashbyhq.com/posting-api/job-board/{quote(self.board)}"

    def parse(self, payload: Any) -> list[Job]:
        jobs: list[Job] = []
        for item in (payload or {}).get("jobs") or []:
            if item.get("isListed") is False:
                continue
            title = str(item.get("title") or "").strip()
            job_id = item.get("id") or item.get("jobUrl")
            if not title or not job_id:
                continue
            jobs.append(
                Job(
                    source=self.source,
                    board=self.board,
                    company=self.name,
                    job_id=str(job_id),
                    title=title,
                    url=str(item.get("jobUrl") or item.get("applyUrl") or ""),
                    locations=_locations(item),
                    remote=_remote(item),
                    description=str(
                        item.get("descriptionPlain") or html_to_text(item.get("descriptionHtml"))
                    ),
                    published_at=parse_datetime(item.get("publishedAt")),
                )
            )
        return jobs


def _locations(item: dict[str, Any]) -> list[str]:
    values: list[object] = [item.get("location")]
    for extra in item.get("secondaryLocations") or []:
        values.append(extra.get("location"))
        address = extra.get("address") or {}
        address = address.get("postalAddress") or address
        values.append(address.get("addressCountry"))
    postal = (item.get("address") or {}).get("postalAddress") or {}
    values.extend([postal.get("addressLocality"), postal.get("addressCountry")])
    return unique(values)


def _remote(item: dict[str, Any]) -> bool | None:
    workplace = str(item.get("workplaceType") or "").lower()
    if item.get("isRemote") is True or workplace == "remote":
        return True
    if workplace in {"onsite", "hybrid"} or item.get("isRemote") is False:
        return False
    return None
