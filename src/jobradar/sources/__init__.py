from __future__ import annotations

from typing import TYPE_CHECKING

from .arbeitnow import ArbeitnowFeed
from .ashby import AshbyBoard
from .base import Getter, Source
from .greenhouse import GreenhouseBoard
from .lever import LeverBoard

if TYPE_CHECKING:
    from ..config import AppConfig

__all__ = [
    "ArbeitnowFeed",
    "AshbyBoard",
    "GreenhouseBoard",
    "LeverBoard",
    "Source",
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
        else:  # config.py validates sources, so this only fires if the two drift apart
            raise ValueError(f"Unsupported source {board.source!r}")
    if config.arbeitnow_enabled:
        sources.append(ArbeitnowFeed(pages=config.arbeitnow_pages, get=get))
    return sources
