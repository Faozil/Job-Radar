from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

USER_AGENT = "job-radar/0.1 (+https://github.com/Faozil/job-radar)"
MAX_WAIT_SECONDS = 30


class NotFoundError(Exception):
    """The board or resource does not exist (HTTP 404)."""


class FetchError(Exception):
    """The request failed, possibly after retries."""


def request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 20,
    retries: int = 2,
    backoff: float = 1.0,
    redact: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """GET (or POST when a payload is given) a URL and decode the JSON response.

    Retries timeouts, HTTP 429 and HTTP 5xx with exponential backoff. With ``redact=True`` the URL
    never appears in error messages, which matters for URLs that contain a secret (Telegram).
    """
    if not url.startswith("https://"):
        raise ValueError("Only https:// URLs are allowed")
    shown = "<redacted url>" if redact else url
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)  # noqa: S310

    error = FetchError(f"{shown}: request failed")
    for attempt in range(retries + 1):
        wait = backoff * 2**attempt
        try:
            # https only, checked above
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.load(response)
        except urllib.error.HTTPError as exc:
            body = _read_json_body(exc)
            if exc.code == 404:
                raise NotFoundError(shown) from None
            if exc.code != 429 and exc.code < 500:
                raise FetchError(f"{shown}: HTTP {exc.code} {_describe(body)}".rstrip()) from None
            wait = _retry_after(exc, body, default=wait)
            error = FetchError(f"{shown}: HTTP {exc.code}")
        except json.JSONDecodeError:
            raise FetchError(f"{shown}: response was not JSON") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            reason = getattr(exc, "reason", exc)
            error = FetchError(f"{shown}: {reason}")
        if attempt < retries:
            sleep(min(wait, MAX_WAIT_SECONDS))
    raise error


def get_json(url: str, **kwargs: Any) -> Any:
    return request_json(url, **kwargs)


def post_json(url: str, payload: dict[str, Any], **kwargs: Any) -> Any:
    return request_json(url, payload=payload, **kwargs)


def _read_json_body(exc: urllib.error.HTTPError) -> dict[str, Any]:
    try:
        body = json.loads(exc.read().decode("utf-8", errors="replace"))
    except (OSError, ValueError, AttributeError):
        return {}
    return body if isinstance(body, dict) else {}


def _describe(body: dict[str, Any]) -> str:
    return str(body.get("description") or body.get("message") or body.get("error") or "")[:200]


def _retry_after(exc: urllib.error.HTTPError, body: dict[str, Any], default: float) -> float:
    candidates = [
        (body.get("parameters") or {}).get("retry_after"),  # Telegram
        exc.headers.get("Retry-After") if exc.headers else None,
    ]
    for value in candidates:
        try:
            return max(float(value), 0.0)
        except (TypeError, ValueError):
            continue
    return default
