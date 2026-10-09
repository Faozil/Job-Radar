from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .filters import FilterConfig

CONFIG_ENV = "JOB_RADAR_CONFIG"
SOURCES = frozenset({"greenhouse", "lever", "ashby"})
LEVER_REGIONS = frozenset({"global", "eu"})


@dataclass(frozen=True)
class Board:
    source: str
    id: str
    name: str
    region: str = "global"


@dataclass(frozen=True)
class AppConfig:
    boards: tuple[Board, ...]
    filters: FilterConfig
    arbeitnow_enabled: bool = True
    arbeitnow_pages: int = 3
    max_per_run: int = 30


def find_config_path() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        Path(os.environ[CONFIG_ENV]) if os.environ.get(CONFIG_ENV) else None,
        here.parents[1] / "job-radar.toml",  # Lambda zip root (/var/task)
        here.parents[2] / "config" / "job-radar.toml",  # repository checkout
    ]
    for path in candidates:
        if path is not None and path.is_file():
            return path
    raise FileNotFoundError(f"Could not find job-radar.toml; set {CONFIG_ENV} to its path")


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path) if path else find_config_path()
    with config_path.open("rb") as handle:
        return parse_config(tomllib.load(handle))


def parse_config(raw: dict[str, Any]) -> AppConfig:
    rules = raw.get("filters") or {}
    filters = FilterConfig.from_lists(
        title_include=rules.get("title_include") or [],
        title_exclude=rules.get("title_exclude") or [],
        locations=rules.get("locations") or [],
        remote_regions=rules.get("remote_regions") or [],
        flag_languages=rules.get("flag_languages") or [],
        max_age_days=rules.get("max_age_days", 45),
        drop_if_sponsorship_excluded=rules.get("drop_if_sponsorship_excluded", True),
    )
    if not filters.title_include:
        raise ValueError("filters.title_include needs at least one pattern")

    feed = raw.get("arbeitnow") or {}
    max_per_run = int(raw.get("max_per_run", 30))
    if max_per_run < 1:
        raise ValueError("max_per_run must be at least 1")
    return AppConfig(
        boards=_boards(raw.get("boards") or []),
        filters=filters,
        arbeitnow_enabled=bool(feed.get("enabled", True)),
        arbeitnow_pages=int(feed.get("pages", 3)),
        max_per_run=max_per_run,
    )


def _boards(items: list[dict[str, Any]]) -> tuple[Board, ...]:
    boards: list[Board] = []
    seen: set[tuple[str, str]] = set()
    for number, item in enumerate(items, start=1):
        source = str(item.get("source") or "").strip().lower()
        if source not in SOURCES:
            raise ValueError(f"boards #{number}: source must be one of {sorted(SOURCES)}")
        board_id = str(item.get("id") or "").strip()
        if not board_id:
            raise ValueError(f"boards #{number}: id is missing")
        region = str(item.get("region") or "global").strip().lower()
        if source == "lever" and region not in LEVER_REGIONS:
            raise ValueError(f"boards #{number}: Lever region must be 'global' or 'eu'")
        if (source, board_id.lower()) in seen:
            raise ValueError(f"boards #{number}: {source}/{board_id} is listed twice")
        seen.add((source, board_id.lower()))
        boards.append(Board(source, board_id, str(item.get("name") or board_id), region))
    return tuple(boards)
