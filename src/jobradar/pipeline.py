from __future__ import annotations

import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from .filters import FilterConfig, classify, prefilter
from .http import NotFoundError
from .models import FEEDS, SPONSORSHIP_OFFERED, SPONSORSHIP_UNCLEAR, Job
from .notify import Notifier
from .sources import Source
from .store import SeenStore
from .text import normalise

logger = logging.getLogger(__name__)

_SPONSORSHIP_RANK = {SPONSORSHIP_OFFERED: 0, SPONSORSHIP_UNCLEAR: 1}


class AllSourcesFailedError(RuntimeError):
    """Every source failed, which usually means a network problem rather than bad boards."""


@dataclass
class RunResult:
    boards_ok: int = 0
    fetched: int = 0
    matched: int = 0
    new: int = 0
    notified: int = 0
    failed: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def run(
    sources: Sequence[Source],
    filters: FilterConfig,
    store: SeenStore,
    notifier: Notifier,
    *,
    max_per_run: int = 30,
    save: bool = True,
    now: datetime | None = None,
    workers: int = 10,
) -> RunResult:
    now = now or datetime.now(UTC)
    result = RunResult()
    jobs = _fetch_all(sources, result, workers)
    if sources and result.boards_ok == 0:
        raise AllSourcesFailedError("; ".join(f"{k}: {v}" for k, v in result.errors.items()))
    result.fetched = len(jobs)

    candidates = _dedupe(prefilter(jobs, filters, now=now))
    seen = store.seen_keys(job.key for job in candidates)
    unseen = [job for job in candidates if job.key not in seen]
    # Some listings leave out the ad text, so it is fetched only for jobs that could still be sent.
    new_jobs = sorted(classify(_describe(unseen, sources, result, workers), filters), key=_priority)
    result.matched = len(candidates) - len(unseen) + len(new_jobs)
    result.new = len(new_jobs)

    to_send = new_jobs[:max_per_run]
    if to_send:
        notifier.send(to_send, extra=len(new_jobs) - len(to_send), failed=sorted(result.failed))
        if save:  # only after a successful send, so a failed send is retried next run
            store.mark_seen(to_send, now)
    result.notified = len(to_send)
    return result


def _fetch_all(sources: Sequence[Source], result: RunResult, workers: int) -> list[Job]:
    jobs: list[Job] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(sources) or 1))) as pool:
        futures = {pool.submit(source.fetch): source for source in sources}
        for future in as_completed(futures):
            source = futures[future]
            try:
                fetched = future.result()
            except NotFoundError:
                _record_failure(result, source.label, "board not found")
                continue
            except Exception as exc:
                _record_failure(result, source.label, str(exc)[:300])
                continue
            result.boards_ok += 1
            jobs.extend(fetched)
    return jobs


def _describe(
    jobs: list[Job], sources: Sequence[Source], result: RunResult, workers: int
) -> list[Job]:
    by_label = {source.label: source for source in sources}
    groups: dict[str, list[Job]] = {}
    for job in jobs:
        groups.setdefault(f"{job.source}/{job.board}", []).append(job)

    described: list[Job] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(groups) or 1))) as pool:
        futures = {
            pool.submit(by_label[label].describe, group): label for label, group in groups.items()
        }
        for future in as_completed(futures):
            try:
                described.extend(future.result())
            except Exception as exc:
                _record_failure(result, futures[future], f"could not read the ads: {exc}"[:300])
    return described


def _record_failure(result: RunResult, label: str, reason: str) -> None:
    logger.warning("source failed: %s: %s", label, reason)
    result.failed.append(label)
    result.errors[label] = reason


def _dedupe(jobs: list[Job]) -> list[Job]:
    unique: dict[tuple[str, str, str], Job] = {}
    # Company boards sort before the feeds, so their copy of a duplicate role is the one kept.
    for job in sorted(jobs, key=lambda item: item.source in FEEDS):
        place = normalise(job.locations[0]) if job.locations else ""
        unique.setdefault((normalise(job.company), normalise(job.title), place), job)
    return list(unique.values())


def _priority(job: Job) -> tuple[int, float, str]:
    published = job.published_at.timestamp() if job.published_at else 0.0
    return (_SPONSORSHIP_RANK.get(job.sponsorship, 2), -published, job.company.lower())
