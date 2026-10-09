from __future__ import annotations

import smtplib
import ssl
from datetime import UTC, datetime

import pytest

from conftest import make_job
from jobradar.models import SPONSORSHIP_OFFERED
from jobradar.notify import (
    ConsoleNotifier,
    EmailNotifier,
    NotifyError,
    build_email,
    location_summary,
)

ADDRESS = "me@example.com"
APP_PASSWORD = "abcd efgh ijkl mnop"
SENT_AT = datetime(2026, 10, 9, 7, 0, tzinfo=UTC)


def fake_smtp(log, error=None):
    class FakeSmtp:
        def __init__(self, host, port, *, timeout, context):
            log.append(("connect", host, port, context))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def login(self, user, password):
            if error:
                raise error
            log.append(("login", user, password))

        def send_message(self, message):
            log.append(("send", message))

    return FakeSmtp


def bodies(message):
    plain = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()
    return plain, html


def test_email_has_plain_and_escaped_html_parts():
    job = make_job(
        title="SRE <Platform> & Ops",
        company="A&B",
        url='https://example.com/jobs?id=1&x="2"',
        sponsorship=SPONSORSHIP_OFFERED,
        flags=["Asks for German"],
    )
    message = build_email([job], address=ADDRESS, now=SENT_AT)

    assert message["Subject"] == "Job Radar: 1 new role (9 Oct)"
    assert message["From"] == f"Job Radar <{ADDRESS}>"
    assert message["To"] == ADDRESS
    plain, html = bodies(message)
    assert "SRE <Platform> & Ops\nA&B · Berlin, Germany\n" in plain
    assert "Mentions visa or relocation support · Asks for German" in plain
    assert 'href="https://example.com/jobs?id=1&amp;x=&quot;2&quot;">SRE &lt;Platform&gt;' in html
    assert "A&amp;B · Berlin, Germany" in html


def test_only_web_links_are_clickable():
    _, html = bodies(build_email([make_job(url="javascript:alert(1)")], address=ADDRESS))
    assert "href" not in html


def test_footer_counts_held_jobs_and_failed_boards():
    message = build_email(
        [make_job()], address=ADDRESS, extra=4, failed=["lever/acme"], now=SENT_AT
    )
    assert message["Subject"] == "Job Radar: 5 new roles (9 Oct)"
    plain, html = bodies(message)
    assert "4 more will come in the next run." in plain
    assert "Could not read: lever/acme" in html


def test_location_summary():
    assert location_summary(make_job(locations=["A", "B", "C", "D", "E"])) == "A, B, C +2 more"
    assert location_summary(make_job(locations=[], remote=True)) == "Remote"
    assert location_summary(make_job(locations=[])) == "Location not listed"


def test_digest_is_sent_over_verified_tls():
    log = []
    EmailNotifier(ADDRESS, APP_PASSWORD, smtp=fake_smtp(log)).send([make_job()])

    (_, host, port, context), login, (_, message) = log
    assert (host, port) == ("smtp.gmail.com", 465)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    assert login == ("login", ADDRESS, "abcdefghijklmnop")
    assert message["To"] == ADDRESS


def test_smtp_errors_are_reported_without_the_password():
    refused = smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
    notifier = EmailNotifier(ADDRESS, APP_PASSWORD, smtp=fake_smtp([], error=refused))
    with pytest.raises(NotifyError, match="not accepted") as error:
        notifier.send([make_job()])
    assert "abcd" not in str(error.value)


def test_a_dropped_connection_points_at_the_settings():
    dropped = smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
    notifier = EmailNotifier(ADDRESS, APP_PASSWORD, smtp=fake_smtp([], error=dropped))
    with pytest.raises(NotifyError, match="check the address and app password"):
        notifier.send_test()


def test_test_email():
    log = []
    EmailNotifier(ADDRESS, APP_PASSWORD, smtp=fake_smtp(log)).send_test()
    assert log[-1][1]["Subject"] == "Job Radar test"


@pytest.mark.parametrize(("address", "password"), [("not-an-address", "x"), (ADDRESS, "")])
def test_email_settings_are_required(address, password):
    with pytest.raises(ValueError):
        EmailNotifier(address, password)


def test_console_notifier_prints_plain_text():
    lines = []
    ConsoleNotifier(write=lines.append).send([make_job()], extra=1, failed=["lever/x"])
    output = "\n".join(lines)
    assert "2 new role(s)" in output
    assert "DevOps Engineer" in output
    assert "https://example.com/jobs/1" in output
    assert "Could not read: lever/x" in output
