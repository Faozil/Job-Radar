"""Greenhouse Job Board API: https://developers.greenhouse.io/job-board.html"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..models import Job
from ..text import html_to_text, parse_datetime, unique
from .base import Source


class GreenhouseBoard(Source):
    source = "greenhouse"

    def url(self) -> str:
        return f"https://boards-api.greenhouse.io/v1/boards/{quote(self.board)}/jobs?content=true"

    def parse(self, payload: Any) -> list[Job]:
        jobs: list[Job] = []
        for item in (payload or {}).get("jobs") or []:
            title = str(item.get("title") or "").strip()
            if not title or item.get("id") is None:
                continue
            jobs.append(
                Job(
                    source=self.source,
                    board=self.board,
                    company=self.name or str(item.get("company_name") or self.board),
                    job_id=str(item["id"]),
                    title=title,
                    url=str(item.get("absolute_url") or ""),
                    locations=_locations(item),
                    description=html_to_text(item.get("content")),
                    published_at=parse_datetime(
                        item.get("first_published") or item.get("updated_at")
                    ),
                )
            )
        return jobs


def _locations(item: dict[str, Any]) -> list[str]:
    # location.name can hold several places ("Remote, Canada; Remote, UK") or just "Hybrid", so
    # offices and any "location" custom field (Cloudflare uses one) are added too.
    values: list[object] = []
    name = (item.get("location") or {}).get("name") or ""
    values.extend(name.split(";"))
    values.extend(office.get("name") for office in item.get("offices") or [])
    for field in item.get("metadata") or []:
        if "location" not in str(field.get("name") or "").lower():
            continue
        value = field.get("value")
        if isinstance(value, list):
            values.extend(value)
        else:
            values.append(value)
    return unique(values)
