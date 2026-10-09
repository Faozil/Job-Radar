from __future__ import annotations

import html
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

_BLOCK_TAG_RE = re.compile(r"</?(?:p|div|br|li|ul|ol|h[1-6]|tr|section)\b[^>]*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def html_to_text(value: str | None) -> str:
    """Convert HTML, including entity-escaped HTML as Greenhouse returns it, to plain text."""
    if not value:
        return ""
    text = html.unescape(value)
    text = _BLOCK_TAG_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _SPACE_RE.sub(" ", text)
    lines = (line.strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def parse_datetime(value: object) -> datetime | None:
    """Parse ISO 8601 and RSS (RFC 822) dates and Unix timestamps (s or ms) to aware datetimes."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        seconds = value / 1000 if value > 100_000_000_000 else value
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def unique(values: Iterable[object]) -> list[str]:
    """Collapse whitespace, drop blanks and remove case-insensitive duplicates, keeping order."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = " ".join(str(value or "").split())
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            result.append(cleaned)
    return result


def normalise(value: str) -> str:
    """Lowercase and strip everything but letters and digits, for fuzzy matching."""
    return _NON_ALNUM_RE.sub("", value.lower())
