from __future__ import annotations

from typing import TYPE_CHECKING

from .arbeitnow import ArbeitnowFeed
from .ashby import AshbyBoard
from .base import Getter, Source
from .bundesagentur import BundesagenturFeed
from .greenhouse import GreenhouseBoard
from .jobicy import JobicyFeed
from .lever import LeverBoard
from .smartrecruiters import SmartRecruitersBoard
from .weworkremotely import WeWorkRemotelyFeed

if TYPE_CHECKING:
    from ..config import AppConfig

__all__ = [
    "ArbeitnowFeed",
    "AshbyBoard",
    "BundesagenturFeed",
    "GreenhouseBoard",
    "JobicyFeed",
    "LeverBoard",
    "SmartRecruitersBoard",
    "Source",
    "WeWorkRemotelyFeed",
    "build_sources",
]


def build_sources(config: AppConfig, get: Getter | None = None) -> list[Source]:
    sources: list[Source] = []
    for board in config.boards:
        if board.source == "greenhouse":
            sources.append(GreenhouseBoard(board.id, board.name, get=get))
        elif board.source == "lever":
            sources.append(LeverBoard(board.id, board.name, region=board.region, get=get))
        elif board.source == "ashby":
            sources.append(AshbyBoard(board.id, board.name, get=get))
        elif board.source == "smartrecruiters":
            sources.append(SmartRecruitersBoard(board.id, board.name, get=get))
        else:  # config.py validates sources, so this only fires if the two drift apart
            raise ValueError(f"Unsupported source {board.source!r}")

    for name, settings in config.feeds.items():
        if name == "arbeitnow":
            sources.append(ArbeitnowFeed(**settings, get=get))
        elif name == "bundesagentur":
            sources.append(BundesagenturFeed(**settings, get=get))
        elif name == "jobicy":
            sources.append(JobicyFeed(**settings, get=get))
        elif name == "weworkremotely":
            sources.append(WeWorkRemotelyFeed(**settings))
        else:
            raise ValueError(f"Unsupported feed {name!r}")
    return sources
