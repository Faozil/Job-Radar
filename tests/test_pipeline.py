from __future__ import annotations

import pytest

from conftest import NOW, make_job
from jobradar.filters import FilterConfig
from jobradar.http import FetchError, NotFoundError
from jobradar.notify import NotifyError
from jobradar.pipeline import AllSourcesFailedError, run
from jobradar.store import MemoryStore

FILTERS = FilterConfig.from_lists(title_include=["devops", "sre"], locations=["berlin"])


class FakeSource:
    def __init__(self, label, jobs=None, error=None, describe=None):
        self.label = label
        self.described = []
        self._jobs = jobs or []
        self._error = error
        self._describe = describe

    def fetch(self):
        if self._error:
            raise self._error
        return list(self._jobs)

    def describe(self, jobs):
        self.described.extend(jobs)
        return self._describe(jobs) if self._describe else jobs


class FakeNotifier:
    def __init__(self, error=None):
        self.calls = []
        self._error = error

    def send(self, jobs, *, extra=0, failed=()):
        if self._error:
            raise self._error
        self.calls.append({"jobs": list(jobs), "extra": extra, "failed": list(failed)})


def test_sends_new_matches_once():
    source = FakeSource(
        "greenhouse/acme", [make_job(job_id="1"), make_job(job_id="2", title="Chef")]
    )
    store, notifier = MemoryStore(), FakeNotifier()

    first = run([source], FILTERS, store, notifier, now=NOW)
    second = run([source], FILTERS, store, notifier, now=NOW)

    assert (first.fetched, first.matched, first.new, first.notified) == (2, 1, 1, 1)
    assert second.new == 0
    assert len(notifier.calls) == 1
    assert [job.job_id for job in notifier.calls[0]["jobs"]] == ["1"]


def test_failed_boards_are_reported_but_do_not_stop_the_run():
    sources = [
        FakeSource("greenhouse/acme", [make_job()]),
        FakeSource("greenhouse/gone", error=NotFoundError("x")),
        FakeSource("lever/flaky", error=FetchError("timeout")),
    ]
    notifier = FakeNotifier()
    result = run(sources, FILTERS, MemoryStore(), notifier, now=NOW)

    assert result.boards_ok == 1
    assert sorted(result.failed) == ["greenhouse/gone", "lever/flaky"]
    assert result.errors["greenhouse/gone"] == "board not found"
    assert notifier.calls[0]["failed"] == ["greenhouse/gone", "lever/flaky"]


def test_all_sources_failing_raises():
    sources = [FakeSource("a/b", error=FetchError("down")), FakeSource("c/d", error=OSError("x"))]
    with pytest.raises(AllSourcesFailedError):
        run(sources, FILTERS, MemoryStore(), FakeNotifier(), now=NOW)


def test_failed_send_is_retried_next_run():
    source = FakeSource("greenhouse/acme", [make_job()])
    store = MemoryStore()
    with pytest.raises(NotifyError):
        run([source], FILTERS, store, FakeNotifier(error=NotifyError("down")), now=NOW)
    assert store.items == {}

    notifier = FakeNotifier()
    assert run([source], FILTERS, store, notifier, now=NOW).notified == 1


def test_max_per_run_holds_the_rest_for_later():
    jobs = [make_job(job_id=str(n), title=f"DevOps Engineer {n}") for n in range(5)]
    store, notifier = MemoryStore(), FakeNotifier()

    result = run(
        [FakeSource("greenhouse/acme", jobs)], FILTERS, store, notifier, max_per_run=2, now=NOW
    )
    assert (result.new, result.notified) == (5, 2)
    assert notifier.calls[0]["extra"] == 3

    later = run(
        [FakeSource("greenhouse/acme", jobs)], FILTERS, store, notifier, max_per_run=10, now=NOW
    )
    assert later.notified == 3


def test_same_role_on_two_sources_is_sent_once():
    board_job = make_job(
        source="greenhouse", board="grafanalabs", company="Grafana Labs", job_id="9"
    )
    feed_job = make_job(source="arbeitnow", board="feed", company="grafanalabs", job_id="slug-9")
    notifier = FakeNotifier()
    run(
        [
            FakeSource("arbeitnow/feed", [feed_job]),
            FakeSource("greenhouse/grafanalabs", [board_job]),
        ],
        FILTERS,
        MemoryStore(),
        notifier,
        now=NOW,
    )
    sent = notifier.calls[0]["jobs"]
    assert [job.source for job in sent] == ["greenhouse"]


def test_jobs_offering_sponsorship_come_first():
    jobs = [
        make_job(job_id="1", title="SRE", description="Nice office."),
        make_job(job_id="2", title="DevOps Engineer", description="We offer visa sponsorship."),
    ]
    notifier = FakeNotifier()
    run([FakeSource("greenhouse/acme", jobs)], FILTERS, MemoryStore(), notifier, now=NOW)
    assert [job.job_id for job in notifier.calls[0]["jobs"]] == ["2", "1"]


def test_dry_run_does_not_save():
    store = MemoryStore()
    run(
        [FakeSource("greenhouse/acme", [make_job()])],
        FILTERS,
        store,
        FakeNotifier(),
        save=False,
        now=NOW,
    )
    assert store.items == {}


def test_nothing_new_sends_nothing():
    notifier = FakeNotifier()
    result = run([FakeSource("greenhouse/acme", [])], FILTERS, MemoryStore(), notifier, now=NOW)
    assert result.notified == 0
    assert notifier.calls == []


def test_ad_text_is_read_only_for_jobs_that_could_be_sent():
    already_sent = make_job(job_id="3", title="SRE")
    store = MemoryStore()
    store.mark_seen([already_sent], NOW)
    source = FakeSource(
        "greenhouse/acme", [make_job(job_id="1"), make_job(job_id="2", title="Chef"), already_sent]
    )
    result = run([source], FILTERS, store, FakeNotifier(), now=NOW)
    assert [job.job_id for job in source.described] == ["1"]
    assert (result.matched, result.new) == (2, 1)


def test_a_failed_ad_lookup_is_reported_and_retried_next_run():
    def broken(jobs):
        raise FetchError("details are down")

    job = make_job(source="bundesagentur", board="de")
    store, notifier = MemoryStore(), FakeNotifier()
    source = FakeSource("bundesagentur/de", [job], describe=broken)
    result = run([source], FILTERS, store, notifier, now=NOW)
    assert result.failed == ["bundesagentur/de"]
    assert "could not read the ads" in result.errors["bundesagentur/de"]
    assert notifier.calls == []
    assert store.items == {}


def test_ads_are_classified_after_their_text_arrives():
    filters = FilterConfig.from_lists(
        title_include=["devops"], locations=["berlin"], skip_german_ads=True
    )
    german = (
        "Wir suchen für unser Team eine Person, die mit uns die Plattform weiterentwickelt. "
        "Du arbeitest mit Kubernetes und Terraform und bist für die Automatisierung der "
        "Infrastruktur zuständig. Wir bieten dir ein Umfeld, in dem du mit uns wächst und "
        "die Zukunft der Firma mitgestaltest. Das ist nicht nur ein Job, sondern eine Chance "
        "für dich und für uns. Bei uns bekommst du eine faire Bezahlung und ein tolles Team."
    )

    def fill(jobs):
        jobs[0].description = german
        jobs[1].description = "We offer visa sponsorship."
        return jobs

    jobs = [
        make_job(source="bundesagentur", board="de", job_id=n, title=f"DevOps {n}", description="")
        for n in ("1", "2")
    ]
    notifier = FakeNotifier()
    source = FakeSource("bundesagentur/de", jobs, describe=fill)
    run([source], filters, MemoryStore(), notifier, now=NOW)
    [sent] = notifier.calls[0]["jobs"]
    assert (sent.job_id, sent.sponsorship) == ("2", "offered")
