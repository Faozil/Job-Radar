from __future__ import annotations

import json

import pytest

from conftest import make_job
from jobradar import cli, handler, metrics
from jobradar.pipeline import RunResult
from jobradar.store import MemoryStore


class StaticSource:
    label = "greenhouse/acme"

    def __init__(self, jobs):
        self._jobs = jobs

    def fetch(self):
        return list(self._jobs)


class RecordingNotifier:
    def __init__(self):
        self.sent = []

    def send(self, jobs, *, extra=0, failed=()):
        self.sent.extend(jobs)


@pytest.fixture
def lambda_env(monkeypatch):
    monkeypatch.setenv("SEEN_TABLE", "job-radar-seen-jobs")
    monkeypatch.setenv("TELEGRAM_TOKEN_PARAM", "/job-radar/telegram/bot-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID_PARAM", "/job-radar/telegram/chat-id")
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
        handler._ssm_value("/job-radar/telegram/bot-token")


def test_secrets_are_read_once_per_container(monkeypatch, lambda_env):
    calls = []

    class FakeSsm:
        def get_parameter(self, Name, WithDecryption):
            calls.append((Name, WithDecryption))
            return {"Parameter": {"Value": "value-for-" + Name.rsplit("/", 1)[-1]}}

    handler._cache["ssm"] = FakeSsm()
    first = handler._notifier()
    second = handler._notifier()
    assert first is second
    assert calls == [
        ("/job-radar/telegram/bot-token", True),
        ("/job-radar/telegram/chat-id", True),
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


def test_cli_run_without_telegram_settings_fails_fast(monkeypatch, capsys):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert cli.main(["run"]) == 2
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err


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


def test_cli_telegram_chat_id(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake")
    updates = {
        "result": [{"message": {"chat": {"id": 42, "type": "private", "first_name": "Faozil"}}}]
    }
    monkeypatch.setattr(cli, "get_json", lambda url, **kwargs: updates)
    assert cli.main(["telegram-chat-id"]) == 0
    assert "42  (private Faozil)" in capsys.readouterr().out
