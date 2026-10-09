from __future__ import annotations

import json

import pytest

from conftest import make_job
from jobradar import cli, handler, metrics
from jobradar.notify import NotifyError
from jobradar.pipeline import RunResult
from jobradar.store import MemoryStore


class StaticSource:
    label = "greenhouse/acme"

    def __init__(self, jobs):
        self._jobs = jobs

    def fetch(self):
        return list(self._jobs)

    def describe(self, jobs):
        return jobs


class RecordingNotifier:
    def __init__(self):
        self.sent = []

    def send(self, jobs, *, extra=0, failed=()):
        self.sent.extend(jobs)


@pytest.fixture
def lambda_env(monkeypatch):
    monkeypatch.setenv("SEEN_TABLE", "job-radar-seen-jobs")
    monkeypatch.setenv("EMAIL_ADDRESS_PARAM", "/job-radar/email/address")
    monkeypatch.setenv("EMAIL_PASSWORD_PARAM", "/job-radar/email/app-password")
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "job-radar")
    handler._cache.clear()
    yield
    handler._cache.clear()


def test_lambda_handler_runs_the_pipeline_and_emits_metrics(monkeypatch, capsys, lambda_env):
    notifier = RecordingNotifier()
    store = MemoryStore()
    monkeypatch.setattr(handler, "_notifier", lambda: notifier)
    monkeypatch.setattr(handler, "DynamoStore", lambda table: store)
    monkeypatch.setattr(handler, "build_sources", lambda config: [StaticSource([make_job()])])

    summary = handler.lambda_handler({}, None)

    assert summary["notified"] == 1
    assert [job.title for job in notifier.sent] == ["DevOps Engineer"]
    emf = json.loads(capsys.readouterr().out.strip().splitlines()[0])
    assert emf["NewJobs"] == 1
    assert emf["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "JobRadar"


def test_placeholder_secret_gives_a_clear_error(monkeypatch, lambda_env):
    class FakeSsm:
        def get_parameter(self, Name, WithDecryption):
            return {"Parameter": {"Value": "set-me-with-aws-cli"}}

    handler._cache["ssm"] = FakeSsm()
    with pytest.raises(handler.SetupError, match="placeholder"):
        handler._ssm_value("/job-radar/email/app-password")


def test_secrets_are_read_once_per_container(monkeypatch, lambda_env):
    calls = []

    class FakeSsm:
        def get_parameter(self, Name, WithDecryption):
            calls.append((Name, WithDecryption))
            value = "me@example.com" if Name.endswith("/address") else "app-password"
            return {"Parameter": {"Value": value}}

    handler._cache["ssm"] = FakeSsm()
    first = handler._notifier()
    second = handler._notifier()
    assert first is second
    assert calls == [
        ("/job-radar/email/address", True),
        ("/job-radar/email/app-password", True),
    ]


def test_emf_record_shape():
    result = RunResult(fetched=10, matched=3, new=2, notified=2, failed=["a"])
    record = metrics.emf_record(result, "job-radar", now_ms=1)
    assert record["Function"] == "job-radar"
    assert {m["Name"] for m in record["_aws"]["CloudWatchMetrics"][0]["Metrics"]} == {
        "JobsFetched",
        "Matches",
        "NewJobs",
        "BoardErrors",
    }
    assert (record["JobsFetched"], record["BoardErrors"]) == (10, 1)


def test_cli_dry_run_prints_matches(monkeypatch, capsys):
    monkeypatch.setattr(cli, "build_sources", lambda config: [StaticSource([make_job()])])
    assert cli.main(["run", "--dry-run", "--all"]) == 0
    output = capsys.readouterr().out
    assert "DevOps Engineer" in output
    assert "new: 1, sent: 1" in output


def test_cli_run_without_email_settings_fails_fast(monkeypatch, capsys):
    monkeypatch.delenv("EMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("EMAIL_APP_PASSWORD", raising=False)
    assert cli.main(["run"]) == 2
    assert "EMAIL_ADDRESS" in capsys.readouterr().err


def test_cli_check_boards_reports_problems(monkeypatch, capsys):
    from jobradar.http import NotFoundError

    class Missing:
        label = "greenhouse/missing"

        def fetch(self):
            raise NotFoundError("x")

    monkeypatch.setattr(
        cli, "build_sources", lambda config: [StaticSource([make_job()]), Missing()]
    )
    assert cli.main(["check-boards"]) == 1
    output = capsys.readouterr().out
    assert "OK         greenhouse/acme" in output
    assert "NOT FOUND  greenhouse/missing" in output


@pytest.fixture
def email_env(monkeypatch):
    monkeypatch.setenv("EMAIL_ADDRESS", "me@example.com")
    monkeypatch.setenv("EMAIL_APP_PASSWORD", "app-password")


def test_cli_test_email(monkeypatch, capsys, email_env):
    sent = []
    monkeypatch.setattr(cli.EmailNotifier, "send_test", lambda self: sent.append(self))
    assert cli.main(["test-email"]) == 0
    assert len(sent) == 1
    assert "Test email sent" in capsys.readouterr().out


def test_cli_test_email_reports_a_failed_login(monkeypatch, capsys, email_env):
    def refuse(self):
        raise NotifyError("Could not send the email: login refused")

    monkeypatch.setattr(cli.EmailNotifier, "send_test", refuse)
    assert cli.main(["test-email"]) == 1
    assert "login refused" in capsys.readouterr().err
