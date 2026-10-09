from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jobradar.config import AppConfig, Board
from jobradar.filters import FilterConfig
from jobradar.http import FetchError
from jobradar.sources import (
    ArbeitnowFeed,
    AshbyBoard,
    GreenhouseBoard,
    LeverBoard,
    build_sources,
)


class FakeGet:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.urls: list[str] = []

    def __call__(self, url):
        self.urls.append(url)
        return self.responses.pop(0)


def test_greenhouse_parses_locations_offices_metadata_and_content():
    payload = {
        "jobs": [
            {
                "id": 8556658002,
                "title": " Senior Site Reliability Engineer ",
                "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/8556658002",
                "location": {"name": "Hybrid; Remote, EMEA"},
                "offices": [{"name": "Berlin"}],
                "metadata": [
                    {"name": "Job Posting Location", "value": ["London, UK", "Berlin"]},
                    {"name": "Team", "value": "Platform"},
                ],
                "content": "&lt;p&gt;We offer visa sponsorship.&lt;/p&gt;",
                "first_published": "2026-09-30T10:00:00-04:00",
                "updated_at": "2026-10-01T10:00:00-04:00",
            },
            {"id": None, "title": "Ignored"},
        ]
    }
    get = FakeGet(payload)
    jobs = GreenhouseBoard("acme", "Acme", get=get).fetch()

    assert get.urls == ["https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"]
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Senior Site Reliability Engineer"
    assert job.locations == ["Hybrid", "Remote, EMEA", "Berlin", "London, UK"]
    assert job.description == "We offer visa sponsorship."
    assert job.published_at == datetime(2026, 9, 30, 14, tzinfo=UTC)
    assert job.key == "greenhouse:acme:8556658002"


@pytest.mark.parametrize(
    ("region", "host"), [("global", "api.lever.co"), ("eu", "api.eu.lever.co")]
)
def test_lever_url_by_region(region, host):
    board = LeverBoard("acme", "Acme", region=region)
    assert board.url() == f"https://{host}/v0/postings/acme?mode=json"


def test_lever_parses_postings():
    payload = [
        {
            "id": "abc-123",
            "text": "Platform Engineer",
            "categories": {"location": "Vilnius", "allLocations": ["Vilnius", "Kaunas"]},
            "country": "LT",
            "workplaceType": "hybrid",
            "hostedUrl": "https://jobs.lever.co/acme/abc-123",
            "descriptionPlain": "Join us.",
            "lists": [{"text": "Benefits", "content": "<li>Relocation package</li>"}],
            "additionalPlain": "We sponsor your visa.",
            "createdAt": 1_790_000_000_000,
        },
        {"id": "no-title"},
    ]
    jobs = LeverBoard("acme", "Acme", get=FakeGet(payload)).fetch()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.locations == ["Vilnius", "Kaunas", "Lithuania"]
    assert job.remote is False
    assert "Relocation package" in job.description
    assert "We sponsor your visa." in job.description
    assert job.published_at == datetime.fromtimestamp(1_790_000_000, tz=UTC)


def test_lever_error_payload_raises():
    with pytest.raises(FetchError):
        LeverBoard("missing", "Missing", get=FakeGet({"ok": False, "error": "Not found"})).fetch()


def test_lever_rejects_unknown_region():
    with pytest.raises(ValueError):
        LeverBoard("acme", "Acme", region="mars")


def test_ashby_parses_jobs_and_skips_unlisted():
    payload = {
        "jobs": [
            {
                "id": "uuid-1",
                "title": "DevOps Engineer",
                "location": "Amsterdam",
                "secondaryLocations": [
                    {"location": "Berlin", "address": {"addressCountry": "Germany"}}
                ],
                "address": {
                    "postalAddress": {
                        "addressLocality": "Amsterdam",
                        "addressCountry": "Netherlands",
                    }
                },
                "isRemote": False,
                "workplaceType": "Hybrid",
                "jobUrl": "https://jobs.ashbyhq.com/acme/uuid-1",
                "descriptionPlain": "Relocation support available.",
                "publishedAt": "2026-10-01T09:00:00.000+00:00",
                "isListed": True,
            },
            {"id": "uuid-2", "title": "Hidden", "isListed": False},
        ]
    }
    get = FakeGet(payload)
    jobs = AshbyBoard("acme", "Acme", get=get).fetch()
    assert get.urls == ["https://api.ashbyhq.com/posting-api/job-board/acme"]
    assert [job.title for job in jobs] == ["DevOps Engineer"]
    assert jobs[0].locations == ["Amsterdam", "Berlin", "Germany", "Netherlands"]
    assert jobs[0].remote is False
    assert jobs[0].published_at == datetime(2026, 10, 1, 9, tzinfo=UTC)


def test_ashby_remote_flag():
    payload = {"jobs": [{"id": "1", "title": "SRE", "isRemote": True, "jobUrl": "https://x"}]}
    assert AshbyBoard("acme", "Acme", get=FakeGet(payload)).fetch()[0].remote is True


def test_arbeitnow_paginates_until_empty_or_limit():
    page = {
        "data": [
            {
                "slug": "devops-engineer-berlin-1",
                "company_name": "Acme GmbH",
                "title": "DevOps Engineer",
                "description": "<p>Visa sponsorship available</p>",
                "remote": False,
                "url": "https://www.arbeitnow.com/jobs/companies/acme/devops-engineer-berlin-1",
                "location": "Berlin",
                "created_at": 1_790_000_000,
            }
        ]
    }
    get = FakeGet(page, {"data": []})
    jobs = ArbeitnowFeed(pages=5, get=get).fetch()
    assert len(jobs) == 1
    assert get.urls[-1].endswith("page=2")
    assert jobs[0].key == "arbeitnow:feed:devops-engineer-berlin-1"

    get = FakeGet(page, page, page)
    assert len(ArbeitnowFeed(pages=2, get=get).fetch()) == 2

    get = FakeGet({**page, "links": {"next": None}}, page)
    assert len(ArbeitnowFeed(pages=3, get=get).fetch()) == 1


def test_build_sources_from_config():
    config = AppConfig(
        boards=(
            Board("greenhouse", "a", "A"),
            Board("lever", "b", "B", "eu"),
            Board("ashby", "c", "C"),
        ),
        filters=FilterConfig.from_lists(title_include=["devops"]),
        arbeitnow_enabled=True,
    )
    labels = [source.label for source in build_sources(config)]
    assert labels == ["greenhouse/a", "lever/b", "ashby/c", "arbeitnow/feed"]
