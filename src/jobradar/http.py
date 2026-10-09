from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

HEADERS = {
    "User-Agent": "job-radar/0.1 (+https://github.com/Faozil/Job-Radar)",
    "Accept": "application/json",
}
MAX_WAIT_SECONDS = 30


class NotFoundError(Exception):
    """The board or resource does not exist (HTTP 404)."""


class FetchError(Exception):
    """The request failed, possibly after retries."""


def get_json(
    url: str,
    *,
    timeout: float = 20,
    retries: int = 2,
    backoff: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Fetch a URL and decode the JSON. Retries timeouts, 429 and 5xx with exponential backoff."""
    if not url.startswith("https://"):
        raise ValueError("Only https:// URLs are allowed")
    request = urllib.request.Request(url, headers=HEADERS)  # noqa: S310

    error = FetchError(f"{url}: request failed")
    for attempt in range(retries + 1):
        wait = backoff * 2**attempt
        try:
            # https only, checked above
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise NotFoundError(url) from None
            if exc.code != 429 and exc.code < 500:
                raise FetchError(f"{url}: HTTP {exc.code} {_describe(exc)}".rstrip()) from None
            wait = _retry_after(exc, default=wait)
            error = FetchError(f"{url}: HTTP {exc.code}")
        except json.JSONDecodeError:
            raise FetchError(f"{url}: response was not JSON") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            error = FetchError(f"{url}: {getattr(exc, 'reason', exc)}")
        if attempt < retries:
            sleep(min(wait, MAX_WAIT_SECONDS))
    raise error


def _describe(exc: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(exc.read().decode("utf-8", errors="replace"))
    except (OSError, ValueError, AttributeError):
        return ""
    if not isinstance(body, dict):
        return ""
    return str(body.get("message") or body.get("error") or "")[:200]


def _retry_after(exc: urllib.error.HTTPError, default: float) -> float:
    try:
        return max(float(exc.headers.get("Retry-After")), 0.0)
    except (AttributeError, TypeError, ValueError):
        return default
