from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jobradar.config import AppConfig, Board
from jobradar.filters import FilterConfig
from jobradar.http import FetchError
from jobradar.sources import (
    ArbeitnowFeed,
    AshbyBoard,
    BundesagenturFeed,
    GreenhouseBoard,
    JobicyFeed,
    LeverBoard,
    SmartRecruitersBoard,
    WeWorkRemotelyFeed,
    build_sources,
)


class FakeGet:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.urls: list[str] = []
        self.headers: list[dict] = []

    def __call__(self, url, headers=None):
        self.urls.append(url)
        self.headers.append(headers or {})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


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
            Board("smartrecruiters", "D", "D"),
        ),
        filters=FilterConfig.from_lists(title_include=["devops"]),
        feeds={
            "arbeitnow": {"pages": 2},
            "bundesagentur": {"days": 7},
            "jobicy": {},
            "weworkremotely": {},
        },
    )
    labels = [source.label for source in build_sources(config)]
    assert labels == [
        "greenhouse/a",
        "lever/b",
        "ashby/c",
        "smartrecruiters/D",
        "arbeitnow/feed",
        "bundesagentur/de",
        "jobicy/remote",
        "weworkremotely/devops",
    ]


BA_LISTING = {
    "stellenangebotsTitel": "DevOps Engineer (m/w/d)",
    "firma": "Acme GmbH",
    "referenznummer": "10001-1003833222-S",
    "datumErsteVeroeffentlichung": "2026-10-09",
    "stellenlokationen": [
        {"adresse": {"ort": "Berlin", "region": "BERLIN", "land": "DEUTSCHLAND"}},
        {"adresse": {"ort": "Hamburg", "region": "HAMBURG", "land": "DEUTSCHLAND"}},
    ],
}


def test_bundesagentur_searches_with_the_client_id_and_skips_agencies():
    get = FakeGet({"ergebnisliste": [BA_LISTING]})
    [job] = BundesagenturFeed(searches=["DevOps"], days=1, get=get).fetch()

    assert get.headers == [{"X-API-Key": "jobboerse-jobsuche"}]
    for part in (
        "/pc/v6/jobs?",
        "was=DevOps",
        "veroeffentlichtseit=1",
        "pav=false",
        "zeitarbeit=false",
    ):
        assert part in get.urls[0]
    assert (job.title, job.company) == ("DevOps Engineer (m/w/d)", "Acme GmbH")
    assert job.locations == ["Berlin", "Hamburg", "Deutschland"]
    assert job.url == "https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-1003833222-S"
    assert job.published_at == datetime(2026, 10, 9, tzinfo=UTC)
    assert job.key == "bundesagentur:de:10001-1003833222-s"


def test_bundesagentur_pages_and_drops_duplicates_across_searches():
    full_page = {"ergebnisliste": [{**BA_LISTING, "referenznummer": str(n)} for n in range(100)]}
    get = FakeGet(full_page, {"ergebnisliste": [BA_LISTING]}, {"ergebnisliste": [BA_LISTING]})
    jobs = BundesagenturFeed(searches=["DevOps", "Kubernetes"], get=get).fetch()
    assert len(jobs) == 101
    assert ["page=2" in url for url in get.urls] == [False, True, False]


def test_bundesagentur_only_accepts_periods_the_api_supports():
    with pytest.raises(ValueError, match="0, 1, 7, 14, 28"):
        BundesagenturFeed(days=2)


def test_bundesagentur_reads_the_ad_and_skips_jobs_it_cannot_read():
    details = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/"
    answers = {
        details + "MTAwMDEtMTAwMzgzMzIyMi1T": {"stellenangebotsBeschreibung": "We sponsor visas."},
        details + "Mg==": FetchError("down"),
    }
    calls = []

    def get(url, headers=None):
        calls.append((url, headers))
        answer = answers[url]
        if isinstance(answer, Exception):
            raise answer
        return answer

    jobs = BundesagenturFeed(get=FakeGet()).parse(
        [BA_LISTING, {**BA_LISTING, "referenznummer": "2"}]
    )
    [described] = BundesagenturFeed(get=get).describe(jobs)
    assert described.description == "We sponsor visas."
    assert {headers["X-API-Key"] for _, headers in calls} == {"jobboerse-jobsuche"}


def test_smartrecruiters_searches_pages_and_reads_the_ad():
    listing = {
        "id": "744000153731048",
        "name": "DevOps Engineer",
        "releasedDate": "2026-10-06T11:11:19.649Z",
        "location": {"fullLocation": "Cluj-Napoca, CJ, Romania", "remote": False},
    }
    detail = {
        "postingUrl": "https://jobs.smartrecruiters.com/Endava/744000153731048-devops-engineer",
        "jobAd": {
            "sections": {
                "jobDescription": {"text": "<p>Run our Kubernetes platform.</p>"},
                "additionalInformation": {"text": "<p>Relocation support available.</p>"},
            }
        },
    }
    get = FakeGet({"content": [listing]}, {"content": []}, {"content": [listing]}, detail)
    board = SmartRecruitersBoard("Endava", "Endava", get=get)
    [job] = board.fetch()
    assert [url.split("?")[1].split("&")[0] for url in get.urls] == [
        "q=devops",
        "q=kubernetes",
        "q=terraform",
    ]
    assert job.locations == ["Cluj-Napoca, CJ, Romania"]

    [job] = board.describe([job])
    assert (
        get.urls[-1]
        == "https://api.smartrecruiters.com/v1/companies/Endava/postings/744000153731048"
    )
    assert job.description == "Run our Kubernetes platform.\nRelocation support available."
    assert job.url.endswith("744000153731048-devops-engineer")


def test_jobicy_merges_tags_and_splits_regions():
    item = {
        "id": 101,
        "jobTitle": "Senior DevOps &amp; SRE",
        "companyName": "Acme",
        "url": "https://jobicy.com/jobs/101-senior-devops",
        "jobGeo": "EMEA,  Ireland",
        "jobDescription": "<p>Fully remote.</p>",
        "pubDate": "2026-10-08 12:30:00",
    }
    get = FakeGet({"jobs": [item]}, {"jobs": [item, {"id": None, "jobTitle": "x"}]})
    [job] = JobicyFeed(tags=["devops", "sre"], get=get).fetch()
    assert job.title == "Senior DevOps & SRE"
    assert job.locations == ["EMEA", "Ireland"]
    assert job.remote is True
    assert job.published_at == datetime(2026, 10, 8, 12, 30, tzinfo=UTC)


WWR_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Acme: DevOps Engineer</title>
    <region>Anywhere in the World</region>
    <description>&lt;p&gt;We sponsor visas.&lt;/p&gt;</description>
    <pubDate>Tue, 06 Oct 2026 10:00:00 +0000</pubDate>
    <link>https://weworkremotely.com/remote-jobs/acme-devops-engineer</link>
  </item>
  <item><title>No link here</title></item>
</channel></rss>"""


def test_we_work_remotely_reads_the_rss_feed():
    urls = []
    feed = WeWorkRemotelyFeed(fetch=lambda url: urls.append(url) or WWR_FEED)
    [job] = feed.fetch()
    assert urls == ["https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss"]
    assert (job.company, job.title) == ("Acme", "DevOps Engineer")
    assert job.locations == ["Anywhere in the World"]
    assert job.description == "We sponsor visas."
    assert job.published_at == datetime(2026, 10, 6, 10, tzinfo=UTC)
    assert job.key == "weworkremotely:devops:acme-devops-engineer"
