from __future__ import annotations

import pytest

from conftest import make_job
from jobradar.models import SPONSORSHIP_OFFERED
from jobradar.notify import (
    ConsoleNotifier,
    NotifyError,
    TelegramNotifier,
    build_messages,
    location_summary,
)

FAKE_TOKEN = "fake-token-for-tests"


def test_message_escapes_html_and_shows_details():
    job = make_job(
        title="SRE <Platform> & Ops",
        company="A&B",
        url='https://example.com/jobs?id=1&x="2"',
        sponsorship=SPONSORSHIP_OFFERED,
        flags=["Asks for German"],
    )
    [message] = build_messages([job])
    assert message.startswith("<b>Job Radar</b>: 1 new role\n\n")
    assert "<b>SRE &lt;Platform&gt; &amp; Ops</b>" in message
    assert "A&amp;B · Berlin, Germany" in message
    assert "Mentions visa or relocation support · Asks for German" in message
    assert 'href="https://example.com/jobs?id=1&amp;x=&quot;2&quot;"' in message


def test_long_digests_are_split():
    jobs = [make_job(job_id=str(n), title=f"DevOps Engineer {n} " + "x" * 150) for n in range(60)]
    messages = build_messages(jobs, max_len=1000)
    assert len(messages) > 1
    assert all(len(message) <= 1000 for message in messages)
    assert messages[1].startswith("<b>Job Radar</b> (continued)")
    assert sum(message.count("Open the job") for message in messages) == 60


def test_footer_mentions_held_jobs_and_failed_boards():
    [message] = build_messages([make_job()], extra=4, failed=[f"greenhouse/b{n}" for n in range(7)])
    assert "<b>Job Radar</b>: 5 new roles" in message
    assert "4 more will come in the next run." in message
    assert (
        "greenhouse/b0, greenhouse/b1, greenhouse/b2, greenhouse/b3, greenhouse/b4 and 2 more"
        in message
    )


def test_location_summary():
    assert location_summary(make_job(locations=["A", "B", "C", "D", "E"])) == "A, B, C +2 more"
    assert location_summary(make_job(locations=[], remote=True)) == "Remote"
    assert location_summary(make_job(locations=[])) == "Location not listed"


def test_telegram_posts_each_message_with_redacted_url():
    calls = []

    def fake_post(url, payload, **kwargs):
        calls.append((url, payload, kwargs))
        return {"ok": True}

    notifier = TelegramNotifier(FAKE_TOKEN, "12345", post=fake_post, sleep=lambda _: None)
    notifier.send([make_job()])

    [(url, payload, kwargs)] = calls
    assert url == f"https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage"
    assert payload["chat_id"] == "12345"
    assert payload["parse_mode"] == "HTML"
    assert payload["link_preview_options"] == {"is_disabled": True}
    assert kwargs == {"redact": True}


def test_telegram_rejection_raises_without_leaking_the_token():
    notifier = TelegramNotifier(
        FAKE_TOKEN,
        "12345",
        post=lambda *a, **k: {"ok": False, "description": "Bad Request: chat not found"},
        sleep=lambda _: None,
    )
    with pytest.raises(NotifyError) as error:
        notifier.send([make_job()])
    assert "chat not found" in str(error.value)
    assert FAKE_TOKEN not in str(error.value)


def test_telegram_requires_credentials():
    with pytest.raises(ValueError):
        TelegramNotifier("", "1")


def test_console_notifier_prints_plain_text():
    lines = []
    ConsoleNotifier(write=lines.append).send([make_job()], extra=1, failed=["lever/x"])
    output = "\n".join(lines)
    assert "2 new role(s)" in output
    assert "DevOps Engineer" in output
    assert "https://example.com/jobs/1" in output
    assert "Could not read: lever/x" in output
