from __future__ import annotations

import pytest

from jobradar.config import SOURCES, find_config_path, parse_config

MINIMAL = {"filters": {"title_include": ["devops"]}}


def test_repository_config_is_valid(app_config):
    assert app_config.boards, "at least one board should be configured"
    assert all(board.source in SOURCES for board in app_config.boards)
    assert app_config.filters.title_include
    assert app_config.max_per_run >= 1


def test_config_is_found_from_the_package(monkeypatch):
    monkeypatch.delenv("JOB_RADAR_CONFIG", raising=False)
    assert find_config_path().name == "job-radar.toml"


def test_environment_variable_overrides_the_path(monkeypatch, tmp_path):
    custom = tmp_path / "custom.toml"
    custom.write_text('[filters]\ntitle_include = ["sre"]\n')
    monkeypatch.setenv("JOB_RADAR_CONFIG", str(custom))
    assert find_config_path() == custom


def test_defaults():
    config = parse_config(MINIMAL)
    assert config.boards == ()
    assert config.arbeitnow_enabled is True
    assert config.filters.max_age_days == 45


@pytest.mark.parametrize(
    ("boards", "message"),
    [
        ([{"source": "workday", "id": "x"}], "source must be one of"),
        ([{"source": "greenhouse"}], "id is missing"),
        ([{"source": "lever", "id": "x", "region": "mars"}], "Lever region"),
        ([{"source": "ashby", "id": "x"}, {"source": "ashby", "id": "X"}], "listed twice"),
    ],
)
def test_bad_boards_are_rejected(boards, message):
    with pytest.raises(ValueError, match=message):
        parse_config({**MINIMAL, "boards": boards})


def test_title_patterns_are_required():
    with pytest.raises(ValueError, match="title_include"):
        parse_config({"filters": {}})


def test_max_per_run_must_be_positive():
    with pytest.raises(ValueError, match="max_per_run"):
        parse_config({**MINIMAL, "max_per_run": 0})
