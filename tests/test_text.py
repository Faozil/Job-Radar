from datetime import UTC, datetime, timedelta, timezone

from jobradar.text import html_to_text, normalise, parse_datetime, unique


def test_html_to_text_handles_entity_escaped_html():
    escaped = (
        "&lt;p&gt;We offer &lt;strong&gt;visa sponsorship&lt;/strong&gt; &amp;amp; more.&lt;/p&gt;"
    )
    assert html_to_text(escaped) == "We offer visa sponsorship & more."


def test_html_to_text_keeps_line_breaks_between_blocks():
    assert html_to_text("<ul><li>Terraform</li><li>Kubernetes</li></ul>") == "Terraform\nKubernetes"
    assert html_to_text(None) == ""


def test_parse_datetime_formats():
    assert parse_datetime("2026-09-30T10:00:00-04:00") == datetime(
        2026, 9, 30, 10, tzinfo=timezone(timedelta(hours=-4))
    )
    assert parse_datetime("2026-09-30T10:00:00.000Z") == datetime(2026, 9, 30, 10, tzinfo=UTC)
    assert parse_datetime(1_790_000_000) == datetime.fromtimestamp(1_790_000_000, tz=UTC)
    assert parse_datetime(1_790_000_000_000) == datetime.fromtimestamp(1_790_000_000, tz=UTC)
    assert parse_datetime("2026-09-30").tzinfo is UTC
    assert parse_datetime("not a date") is None
    assert parse_datetime(None) is None
    assert parse_datetime(True) is None


def test_unique_and_normalise():
    assert unique(["Berlin", " berlin ", None, "", "Remote,  EMEA"]) == ["Berlin", "Remote, EMEA"]
    assert normalise("Grafana Labs") == normalise("grafanalabs") == "grafanalabs"


def test_parse_datetime_reads_rss_dates():
    expected = datetime(2026, 10, 6, 10, tzinfo=UTC)
    assert parse_datetime("Tue, 06 Oct 2026 10:00:00 +0000") == expected
    assert parse_datetime("Tue, 06 Oct 2026 11:00:00 +0100") == expected
