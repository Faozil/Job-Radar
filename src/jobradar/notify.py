from __future__ import annotations

import html
import smtplib
import ssl
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid
from typing import Any

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


def footer_lines(extra: int, failed: Sequence[str]) -> list[str]:
    lines = []
    if extra:
        lines.append(f"{extra} more will come in the next run.")
    if failed:
        lines.append("Could not read: " + ", ".join(failed))
    return lines


def plain_text(jobs: Sequence[Job], *, extra: int = 0, failed: Sequence[str] = ()) -> str:
    blocks = [
        f"{job.title}\n{job.company} · {location_summary(job)}\n{details(job)}\n{job.url}"
        for job in jobs
    ]
    return "\n\n".join([*blocks, *footer_lines(extra, failed)]) + "\n"


def html_text(jobs: Sequence[Job], *, extra: int = 0, failed: Sequence[str] = ()) -> str:
    parts = []
    for job in jobs:
        title = html.escape(job.title)
        if job.url.startswith(("https://", "http://")):
            title = f'<a href="{html.escape(job.url, quote=True)}">{title}</a>'
        place = html.escape(f"{job.company} · {location_summary(job)}")
        info = html.escape(details(job))
        parts.append(f'<p><b>{title}</b><br>{place}<br><span style="color:#666">{info}</span></p>')
    footer = "<br>".join(html.escape(line) for line in footer_lines(extra, failed))
    if footer:
        parts.append(f'<p style="color:#666">{footer}</p>')
    return "<html><body>\n" + "\n".join(parts) + "\n</body></html>\n"


def build_email(
    jobs: Sequence[Job],
    *,
    address: str,
    extra: int = 0,
    failed: Sequence[str] = (),
    now: datetime | None = None,
) -> EmailMessage:
    now = now or datetime.now(UTC)
    total = len(jobs) + extra
    # The date keeps Gmail from threading every digest into one conversation.
    subject = f"Job Radar: {total} new role{'' if total == 1 else 's'} ({now.day} {now:%b})"
    message = _new_message(address, subject, now)
    message.set_content(plain_text(jobs, extra=extra, failed=failed))
    message.add_alternative(html_text(jobs, extra=extra, failed=failed), subtype="html")
    return message


def _new_message(address: str, subject: str, now: datetime) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr(("Job Radar", address))
    message["To"] = address
    message["Date"] = format_datetime(now)
    message["Message-ID"] = make_msgid(domain=address.rpartition("@")[2])
    return message


class EmailNotifier(Notifier):
    """Emails the digest from the address to itself, over SMTP with TLS."""

    def __init__(
        self,
        address: str,
        password: str,
        *,
        host: str = "smtp.gmail.com",
        port: int = 465,
        smtp: Callable[..., Any] = smtplib.SMTP_SSL,
        timeout: float = 30,
    ) -> None:
        if "@" not in address or not password:
            raise ValueError("An email address and an app password are required")
        self._address = address.strip()
        self._password = "".join(password.split())  # Google shows app passwords in groups of four
        self._host = host
        self._port = port
        self._smtp = smtp
        self._timeout = timeout

    def send(self, jobs: Sequence[Job], *, extra: int = 0, failed: Sequence[str] = ()) -> None:
        self._deliver(build_email(jobs, address=self._address, extra=extra, failed=failed))

    def send_test(self) -> None:
        message = _new_message(self._address, "Job Radar test", datetime.now(UTC))
        message.set_content("Your Job Radar email settings work.\n")
        self._deliver(message)

    def _deliver(self, message: EmailMessage) -> None:
        tls = ssl.create_default_context()
        try:
            with self._smtp(self._host, self._port, timeout=self._timeout, context=tls) as server:
                server.login(self._address, self._password)
                server.send_message(message)
        except smtplib.SMTPServerDisconnected as exc:
            # Gmail hangs up, without an error code, on a login for an unknown address.
            raise NotifyError(
                "The mail server closed the connection; check the address and app password"
            ) from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise NotifyError(f"Could not send the email: {exc}") from exc


class ConsoleNotifier(Notifier):
    """Prints the digest instead of sending it. Used by dry runs."""

    def __init__(self, write: Callable[[str], Any] = print) -> None:
        self._write = write

    def send(self, jobs: Sequence[Job], *, extra: int = 0, failed: Sequence[str] = ()) -> None:
        self._write(f"{len(jobs) + extra} new role(s)\n")
        self._write(plain_text(jobs, extra=extra, failed=failed))
