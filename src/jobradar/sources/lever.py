"""Lever Postings API: https://github.com/lever/postings-api"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..http import FetchError
from ..models import Job
from ..text import html_to_text, parse_datetime, unique
from .base import Getter, Source

HOSTS = {"global": "api.lever.co", "eu": "api.eu.lever.co"}

# Lever gives a two-letter country code; names make location matching work.
COUNTRY_NAMES = {
    "AT": "Austria",
    "CA": "Canada",
    "CH": "Switzerland",
    "CZ": "Czechia",
    "DE": "Germany",
    "EE": "Estonia",
    "ES": "Spain",
    "FR": "France",
    "GB": "United Kingdom",
    "IE": "Ireland",
    "LT": "Lithuania",
    "LV": "Latvia",
    "NG": "Nigeria",
    "NL": "Netherlands",
    "PL": "Poland",
    "PT": "Portugal",
    "RO": "Romania",
    "US": "United States",
}


class LeverBoard(Source):
    source = "lever"

    def __init__(self, board: str, name: str, region: str = "global", get: Getter | None = None):
        super().__init__(board, name, get)
        if region not in HOSTS:
            raise ValueError(f"Unknown Lever region {region!r}; use 'global' or 'eu'")
        self.region = region

    def url(self) -> str:
        return f"https://{HOSTS[self.region]}/v0/postings/{quote(self.board)}?mode=json"

    def parse(self, payload: Any) -> list[Job]:
        if isinstance(payload, dict):  # Lever answers errors with {"ok": false, "error": ...}
            raise FetchError(f"{self.label}: {payload.get('error') or 'unexpected response'}")
        jobs: list[Job] = []
        for item in payload or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("text") or "").strip()
            job_id = item.get("id")
            if not title or not job_id:
                continue
            categories = item.get("categories") or {}
            locations: list[object] = [categories.get("location")]
            locations.extend(categories.get("allLocations") or [])
            country = str(item.get("country") or "").upper()
            if country:
                locations.append(COUNTRY_NAMES.get(country, country))
            jobs.append(
                Job(
                    source=self.source,
                    board=self.board,
                    company=self.name,
                    job_id=str(job_id),
                    title=title,
                    url=str(item.get("hostedUrl") or item.get("applyUrl") or ""),
                    locations=unique(locations),
                    remote=_remote(item.get("workplaceType")),
                    description=_description(item),
                    published_at=parse_datetime(item.get("createdAt")),
                )
            )
        return jobs


def _remote(workplace: object) -> bool | None:
    value = str(workplace or "").lower()
    if value == "remote":
        return True
    if value in {"onsite", "on-site", "hybrid"}:
        return False
    return None


def _description(item: dict[str, Any]) -> str:
    parts = [str(item.get("descriptionPlain") or html_to_text(item.get("description")))]
    for section in item.get("lists") or []:
        parts.append(str(section.get("text") or ""))
        parts.append(html_to_text(section.get("content")))
    parts.append(str(item.get("additionalPlain") or html_to_text(item.get("additional"))))
    return "\n".join(part for part in parts if part.strip())
