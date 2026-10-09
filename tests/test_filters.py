from __future__ import annotations

from datetime import timedelta

import pytest

from conftest import NOW, make_job
from jobradar.filters import (
    FilterConfig,
    apply_filters,
    classify_sponsorship,
    language_flags,
    location_ok,
    title_ok,
)
from jobradar.models import (
    SPONSORSHIP_EXCLUDED,
    SPONSORSHIP_OFFERED,
    SPONSORSHIP_UNCLEAR,
    SPONSORSHIP_UNKNOWN,
)


@pytest.mark.parametrize(
    "title",
    [
        "DevOps Engineer",
        "Senior DevSecOps Engineer",
        "Senior Site Reliability Engineer - Access Team",
        "SRE II",
        "Senior Platform Engineer - Observability",
        "Infrastructure Developer (Go)",
        "Senior Engineer, Infrastructure Platform",
        "AI Infrastructure Engineer",
        "Cloud Support Engineer",
        "Cloud Security Engineer",
        "Senior Linux Infrastructure Engineer",
        "Kubernetes Engineer",
        "Release Engineer",
        "Software Engineer, Infrastructure",
        "Systemadministrator Linux (m/w/d)",
        "Linux-Administrator (m/w/d)",
    ],
)
def test_titles_that_match(app_config, title):
    assert title_ok(make_job(title=title), app_config.filters)


@pytest.mark.parametrize(
    "title",
    [
        "Account Executive, Platforms (Nordic Region)",
        "Engineering Manager, Infrastructure - Infrastructure Platform",
        "Staff Software Engineer - Databases SRE | Germany | Remote",
        "Cloud Alliances Business Development Lead",
        "Backend Engineer, Create: Repository Management",
        "IT Solutions Engineer - Google Cloud",
        "Embedded & Desktop Linux Systems Engineer - Optimisation",
        "Director, Product Management - Cloud Security and Shared Capabilities",
        "Working Student DevOps",
        "Associate Director, Maintenance and Reliability Engineering",
    ],
)
def test_titles_that_do_not_match(app_config, title):
    assert not title_ok(make_job(title=title), app_config.filters)


@pytest.mark.parametrize(
    ("locations", "remote", "title"),
    [
        (["Berlin"], None, "DevOps Engineer"),
        (["München"], None, "DevOps Engineer"),
        (["Vilnius, Lithuania"], None, "DevOps Engineer"),
        (["Bucharest"], None, "DevOps Engineer"),
        (["Amsterdam"], None, "DevOps Engineer"),
        (["Home based - Worldwide"], None, "Cloud Support Engineer"),
        (["Remote, EMEA"], None, "SRE"),
        (["EMEA"], True, "SRE"),
        (["Germany (Remote)"], None, "SRE"),
        ([], None, "Senior SRE | Ireland | Remote"),
    ],
)
def test_locations_that_match(app_config, locations, remote, title):
    job = make_job(locations=locations, remote=remote, title=title)
    assert location_ok(job, app_config.filters)


@pytest.mark.parametrize(
    "locations",
    [
        ["Remote, United States"],
        ["Barcelona"],
        ["London, England"],
        ["Remote, Europe"],
        ["Hybrid"],
        ["EMEA"],  # on-site in an unnamed EMEA office is not enough
        [],
    ],
)
def test_locations_that_do_not_match(app_config, locations):
    assert not location_ok(make_job(locations=locations), app_config.filters)


def test_location_terms_respect_word_boundaries():
    filters = FilterConfig.from_lists(title_include=["devops"], locations=["cork"])
    assert location_ok(make_job(locations=["Cork, Ireland"]), filters)
    assert not location_ok(make_job(locations=["New Corktown"]), filters)


def test_empty_location_rules_accept_everything():
    filters = FilterConfig.from_lists(title_include=["devops"])
    assert location_ok(make_job(locations=["Tokyo"]), filters)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("We offer visa sponsorship and a relocation package.", SPONSORSHIP_OFFERED),
        ("We will help you relocate to Berlin.", SPONSORSHIP_OFFERED),
        ("EU Blue Card applications are welcome.", SPONSORSHIP_OFFERED),
        ("Unfortunately we cannot offer visa sponsorship for this role.", SPONSORSHIP_EXCLUDED),
        ("We are not able to sponsor visas.", SPONSORSHIP_EXCLUDED),
        (
            "We\N{RIGHT SINGLE QUOTATION MARK}re unable to sponsor work permits.",
            SPONSORSHIP_EXCLUDED,
        ),
        (
            "This role doesn\N{RIGHT SINGLE QUOTATION MARK}t offer relocation or visa sponsorship.",
            SPONSORSHIP_EXCLUDED,
        ),
        ("Visa sponsorship is not available.", SPONSORSHIP_EXCLUDED),
        ("You must already have the right to work in the Netherlands.", SPONSORSHIP_EXCLUDED),
        ("EU citizens only.", SPONSORSHIP_EXCLUDED),
        ("This position requires an existing work permit.", SPONSORSHIP_EXCLUDED),
        ("The role requires work authorization in Ireland.", SPONSORSHIP_EXCLUDED),
        (
            "We offer relocation support. You must be authorised to work in the EU.",
            SPONSORSHIP_UNCLEAR,
        ),
        ("Join our friendly team in Berlin.", SPONSORSHIP_UNKNOWN),
        ("", SPONSORSHIP_UNKNOWN),
    ],
)
def test_sponsorship_classification(text, expected):
    assert classify_sponsorship(text) == expected


def test_language_flags(app_config):
    assert language_flags("Fluent German is a must.", app_config.filters) == ["Asks for German"]
    assert language_flags("Dutch: C1 level required.", app_config.filters) == ["Asks for Dutch"]
    assert language_flags("Gute Deutschkenntnisse are nice.", app_config.filters) == []
    assert language_flags("We speak English.", app_config.filters) == []


def test_ad_written_in_german_is_flagged(app_config):
    german = (
        "Wir suchen für unser Team eine Person, die mit uns die Plattform weiterentwickelt. "
        "Du arbeitest mit Kubernetes und Terraform und bist für die Automatisierung der "
        "Infrastruktur zuständig. Wir bieten dir ein Umfeld, in dem du mit uns wächst und "
        "die Zukunft der Firma mitgestaltest. Das ist nicht nur ein Job, sondern eine Chance "
        "für dich und für uns. Bei uns bekommst du eine faire Bezahlung und ein tolles Team."
    )
    assert "Ad is in German" in language_flags(german, app_config.filters)


def test_apply_filters_end_to_end(app_config):
    jobs = [
        make_job(job_id="1", description="We offer visa sponsorship."),
        make_job(job_id="2", description="We cannot offer visa sponsorship."),
        make_job(job_id="3", title="Account Executive"),
        make_job(job_id="4", locations=["Paris"]),
        make_job(job_id="5", published_at=NOW - timedelta(days=90)),
        make_job(job_id="6", published_at=None),
    ]
    matched = apply_filters(jobs, app_config.filters, now=NOW)
    assert [job.job_id for job in matched] == ["1", "6"]
    assert matched[0].sponsorship == SPONSORSHIP_OFFERED


def test_excluded_jobs_can_be_kept():
    filters = FilterConfig.from_lists(title_include=["devops"], drop_if_sponsorship_excluded=False)
    job = make_job(description="No visa sponsorship.")
    assert apply_filters([job], filters, now=NOW)[0].sponsorship == SPONSORSHIP_EXCLUDED


def test_invalid_pattern_is_reported():
    with pytest.raises(ValueError, match="Invalid title pattern"):
        FilterConfig.from_lists(title_include=["(unclosed"])
