from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .models import (
    SPONSORSHIP_EXCLUDED,
    SPONSORSHIP_OFFERED,
    SPONSORSHIP_UNCLEAR,
    SPONSORSHIP_UNKNOWN,
    Job,
)

REMOTE_WORDS = ("remote", "home based", "home-based", "work from home", "anywhere", "distributed")

# Sentences that rule sponsorship out.
_NEGATIVE = re.compile(
    "|".join(
        [
            r"\bno\s+(?:visa\s+|work\s+permit\s+)?sponsorship",
            r"\b(?:not|unable|cannot|can\s?not|can't|won't|will\s+not)\s+(?:(?:be\s+)?able\s+)?"
            r"(?:to\s+)?(?:offer|provide|support)?\s*(?:visa\s+|work\s+permit\s+)?sponsor",
            r"\bdo(?:es)?\s*(?:not|n't)\s+(?:offer|provide|support)\s+(?:\w+\s+){0,3}?"
            r"(?:visa\s+)?(?:sponsorship|relocation)",
            r"\bdo(?:es)?\s*(?:not|n't)\s+sponsor",
            r"\bwithout\s+(?:the\s+need\s+for\s+)?(?:visa\s+|work\s+permit\s+)?sponsorship",
            r"\bsponsorship\s+(?:is\s+)?(?:not|unavailable)\b",
            r"\b(?:eu|eea|uk|us)\s+(?:citizens?|nationals?|residents?)\s+only",
            r"\bmust\s+(?:already\s+)?(?:have|hold|possess)\s+(?:a\s+|an\s+|the\s+)?"
            r"(?:valid\s+|existing\s+|current\s+)?(?:legal\s+)?(?:right|authori[sz]ation|permission)"
            r"\s+to\s+work",
            r"\bmust\s+(?:already\s+)?(?:have|hold|possess)\s+(?:a\s+|an\s+)?(?:valid\s+|existing\s+)?"
            r"(?:eu\s+|german\s+|dutch\s+|irish\s+|uk\s+)?work\s+permit",
            r"\bmust\s+be\s+(?:legally\s+)?(?:authori[sz]ed|eligible|entitled|permitted)\s+to\s+work",
            r"\brequires?\s+(?:a\s+|an\s+)?(?:valid\s+|existing\s+|current\s+)?(?:eu\s+)?work\s+"
            r"(?:permit|authori[sz]ation)",
            r"\bno\s+relocation",
            r"\brelocation\s+(?:is\s+)?not\s+(?:offered|provided|available|supported|possible)",
        ]
    ),
    re.IGNORECASE,
)

# Sentences that offer help with visas or relocation.
_POSITIVE = re.compile(
    "|".join(
        [
            r"\bvisa\s+sponsorship",
            r"\bsponsor(?:s|ing|ship)?\s+(?:your\s+|a\s+|the\s+)?(?:work\s+)?visas?\b",
            r"\bvisa\s+(?:support|assistance|process|application)",
            r"\bwork\s+permit\s+(?:support|assistance|sponsorship)",
            r"\brelocation\s+(?:package|support|assistance|bonus|budget|allowance|help)",
            r"\b(?:help|support|assist)\s+(?:you\s+)?(?:with\s+)?(?:your\s+)?relocat",
            r"\bblue\s+card\b",
            r"\bimmigration\s+(?:support|assistance|lawyer|partner|advice)",
            r"\bwe\s+(?:can\s+|will\s+|do\s+)?(?:also\s+)?sponsor\b",
        ]
    ),
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")

LANGUAGE_NAMES = {
    "german": ("german", "deutsch"),
    "dutch": ("dutch", "nederlands"),
    "lithuanian": ("lithuanian", "lietuvių"),
    "romanian": ("romanian", "română", "romana"),
    "polish": ("polish", "polski"),
    "french": ("french", "français"),
}
_LEVEL_BEFORE = (
    r"(?:fluent|fluency|native|proficien\w*|business[\s-]?level|excellent|very\s+good|"
    r"strong|working\s+knowledge|c1|c2|b2)"
)
_LEVEL_AFTER = (
    r"(?:fluent|fluency|native|required|mandatory|essential|a\s+must|must|c1|c2|b2|"
    r"proficien\w*|level|skills?\s+(?:are\s+)?required)"
)
_GERMAN_WORDS = frozenset(
    {
        "und", "wir", "die", "der", "das", "für", "mit", "sie", "ist",
        "nicht", "oder", "auf", "bei", "ein", "eine", "zu", "ihre", "unsere",
    }
)  # fmt: skip
_WORD_RE = re.compile(r"[a-zäöüß]+")


@dataclass(frozen=True)
class FilterConfig:
    title_include: tuple[re.Pattern[str], ...]
    title_exclude: tuple[re.Pattern[str], ...] = ()
    locations: tuple[re.Pattern[str], ...] = ()
    remote_regions: tuple[re.Pattern[str], ...] = ()
    flag_languages: tuple[tuple[str, re.Pattern[str]], ...] = ()
    max_age_days: int | None = 45
    drop_if_sponsorship_excluded: bool = True

    @classmethod
    def from_lists(
        cls,
        *,
        title_include: Iterable[str],
        title_exclude: Iterable[str] = (),
        locations: Iterable[str] = (),
        remote_regions: Iterable[str] = (),
        flag_languages: Iterable[str] = (),
        max_age_days: int | None = 45,
        drop_if_sponsorship_excluded: bool = True,
    ) -> FilterConfig:
        return cls(
            title_include=tuple(_regex(pattern) for pattern in title_include),
            title_exclude=tuple(_regex(pattern) for pattern in title_exclude),
            locations=tuple(_term(term) for term in locations),
            remote_regions=tuple(_term(term) for term in remote_regions),
            flag_languages=tuple((lang.lower(), _language(lang)) for lang in flag_languages),
            max_age_days=int(max_age_days) if max_age_days else None,
            drop_if_sponsorship_excluded=bool(drop_if_sponsorship_excluded),
        )


def apply_filters(
    jobs: Iterable[Job], config: FilterConfig, now: datetime | None = None
) -> list[Job]:
    """Return the jobs that match, with sponsorship and flags filled in."""
    now = now or datetime.now(UTC)
    matched: list[Job] = []
    for job in jobs:
        if not (title_ok(job, config) and location_ok(job, config) and is_fresh(job, config, now)):
            continue
        job.sponsorship = classify_sponsorship(job.description)
        if job.sponsorship == SPONSORSHIP_EXCLUDED and config.drop_if_sponsorship_excluded:
            continue
        job.flags = language_flags(job.description, config)
        matched.append(job)
    return matched


def title_ok(job: Job, config: FilterConfig) -> bool:
    title = job.title.lower()
    included = any(pattern.search(title) for pattern in config.title_include)
    return included and not any(pattern.search(title) for pattern in config.title_exclude)


def location_ok(job: Job, config: FilterConfig) -> bool:
    if not config.locations and not config.remote_regions:
        return True
    # Some boards put the country in the title ("SRE | Germany | Remote").
    text = " | ".join([*job.locations, job.title]).lower()
    if any(pattern.search(text) for pattern in config.locations):
        return True
    remote = job.remote is True or any(word in text for word in REMOTE_WORDS)
    return remote and any(pattern.search(text) for pattern in config.remote_regions)


def is_fresh(job: Job, config: FilterConfig, now: datetime) -> bool:
    if config.max_age_days is None or job.published_at is None:
        return True
    return now - job.published_at <= timedelta(days=config.max_age_days)


def classify_sponsorship(description: str) -> str:
    offered = excluded = False
    text = (description or "").replace("\N{RIGHT SINGLE QUOTATION MARK}", "'")
    for sentence in _SENTENCE_SPLIT.split(text):
        # Negatives win: "we can't sponsor visas" also matches a positive pattern.
        if _NEGATIVE.search(sentence):
            excluded = True
        elif _POSITIVE.search(sentence):
            offered = True
    if offered and excluded:
        return SPONSORSHIP_UNCLEAR
    if offered:
        return SPONSORSHIP_OFFERED
    if excluded:
        return SPONSORSHIP_EXCLUDED
    return SPONSORSHIP_UNKNOWN


def language_flags(description: str, config: FilterConfig) -> list[str]:
    flags = [
        f"Asks for {lang.title()}"
        for lang, pattern in config.flag_languages
        if pattern.search(description or "")
    ]
    if _looks_german(description):
        flags.append("Ad is in German")
    return flags


def _looks_german(text: str) -> bool:
    words = _WORD_RE.findall((text or "").lower())
    if len(words) < 40:
        return False
    hits = sum(1 for word in words if word in _GERMAN_WORDS)
    return hits >= 15 and hits / len(words) >= 0.08


def _regex(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"Invalid title pattern {pattern!r}: {exc}") from exc


def _term(term: str) -> re.Pattern[str]:
    cleaned = " ".join(term.lower().split())
    if not cleaned:
        raise ValueError("Location terms cannot be empty")
    return re.compile(rf"(?<!\w){re.escape(cleaned)}(?!\w)")


def _language(lang: str) -> re.Pattern[str]:
    names = LANGUAGE_NAMES.get(lang.lower(), (lang.lower(),))
    alternatives = "|".join(re.escape(name) for name in names)
    return re.compile(
        rf"\b{_LEVEL_BEFORE}\b[^.\n]{{0,40}}\b(?:{alternatives})\b"
        rf"|\b(?:{alternatives})\b[^.\n]{{0,30}}\b{_LEVEL_AFTER}",
        re.IGNORECASE,
    )
