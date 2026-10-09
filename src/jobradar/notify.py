"""Send the digest of new jobs: Telegram in production, the console for dry runs."""

from __future__ import annotations

import html
import time
from collections.abc import Callable, Sequence
from typing import Any

from .http import post_json
from .models import (
    SPONSORSHIP_EXCLUDED,
    SPONSORSHIP_OFFERED,
    SPONSORSHIP_UNCLEAR,
    SPONSORSHIP_UNKNOWN,
    Job,
)

SPONSORSHIP_LABELS = {
    SPONSORSHIP_OFFERED: "Mentions visa or relocation support",
    SPONSORSHIP_UNCLEAR: "Sponsorship unclear, check the ad",
    SPONSORSHIP_UNKNOWN: "Sponsorship not mentioned",
    SPONSORSHIP_EXCLUDED: "Says no sponsorship",
}
TELEGRAM_LIMIT = 3900  # Telegram allows 4096 characters per message; leave some headroom


class NotifyError(Exception):
    """The digest could not be delivered."""


class Notifier:
    def send(self, jobs: Sequence[Job], *, extra: int = 0, failed: Sequence[str] = ()) -> None:
        raise NotImplementedError


def location_summary(job: Job, limit: int = 3) -> str:
    if not job.locations:
        return "Remote" if job.remote else "Location not listed"
    text = ", ".join(job.locations[:limit])
    if len(job.locations) > limit:
        text += f" +{len(job.locations) - limit} more"
    return text


def details(job: Job) -> str:
    text = SPONSORSHIP_LABELS.get(job.sponsorship, job.sponsorship)
    if job.flags:
        text += " · " + ", ".join(job.flags)
    return text


def format_job_html(job: Job) -> str:
    lines = [
        f"<b>{html.escape(job.title[:200])}</b>",
        html.escape(f"{job.company[:100]} · {location_summary(job)}"),
        html.escape(details(job)),
    ]
    if job.url:
        lines.append(f'<a href="{html.escape(job.url, quote=True)}">Open the job</a>')
    return "\n".join(lines)


def build_messages(
    jobs: Sequence[Job],
    *,
    extra: int = 0,
    failed: Sequence[str] = (),
    max_len: int = TELEGRAM_LIMIT,
) -> list[str]:
    """Build the Telegram digest, split into messages that fit Telegram's size limit."""
    total = len(jobs) + extra
    header = f"<b>Job Radar</b>: {total} new role{'' if total == 1 else 's'}"
    footer_lines = []
    if extra:
        footer_lines.append(f"{extra} more will come in the next run.")
    if failed:
        shown = ", ".join(failed[:5]) + (f" and {len(failed) - 5} more" if len(failed) > 5 else "")
        footer_lines.append(f"Could not read: {shown}")
    footer = html.escape("\n".join(footer_lines))

    messages: list[str] = []
    current = header
    for block in (format_job_html(job) for job in jobs):
        if len(current) + 2 + len(block) > max_len:
            messages.append(current)
            current = "<b>Job Radar</b> (continued)"
        current = f"{current}\n\n{block}"
    if footer:
        if len(current) + 2 + len(footer) > max_len:
            messages.append(current)
            current = footer
        else:
            current = f"{current}\n\n{footer}"
    messages.append(current)
    return messages


class TelegramNotifier(Notifier):
    API = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        post: Callable[..., Any] = post_json,
        sleep: Callable[[float], None] = time.sleep,
        pause_seconds: float = 1.0,
    ) -> None:
        if not token or not chat_id:
            raise ValueError("A Telegram bot token and chat id are required")
        self._token = token
        self._chat_id = str(chat_id)
        self._post = post
        self._sleep = sleep
        self._pause = pause_seconds

    def send(self, jobs: Sequence[Job], *, extra: int = 0, failed: Sequence[str] = ()) -> None:
        for index, text in enumerate(build_messages(jobs, extra=extra, failed=failed)):
            if index:
                self._sleep(self._pause)  # stay well under Telegram's per-chat rate limit
            response = self._post(
                self.API.format(token=self._token),
                {
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                },
                redact=True,
            )
            if not isinstance(response, dict) or not response.get("ok"):
                reason = response.get("description") if isinstance(response, dict) else response
                raise NotifyError(f"Telegram rejected the message: {reason}")


class ConsoleNotifier(Notifier):
    """Prints the digest instead of sending it. Used by dry runs."""

    def __init__(self, write: Callable[[str], Any] = print) -> None:
        self._write = write

    def send(self, jobs: Sequence[Job], *, extra: int = 0, failed: Sequence[str] = ()) -> None:
        self._write(f"{len(jobs) + extra} new role(s)\n")
        for job in jobs:
            self._write(f"{job.title}\n  {job.company} · {location_summary(job)}\n  {details(job)}")
            self._write(f"  {job.url}\n")
        if extra:
            self._write(f"...and {extra} more next run")
        if failed:
            self._write("Could not read: " + ", ".join(failed))
