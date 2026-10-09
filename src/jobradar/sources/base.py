from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..http import get_json
from ..models import Job

Getter = Callable[..., Any]


class Source:
    """Fetches one job board (or feed) and turns its API response into Job objects."""

    source = "base"

    def __init__(self, board: str, name: str, get: Getter | None = None) -> None:
        self.board = board
        self.name = name
        self._get = get or get_json

    @property
    def label(self) -> str:
        return f"{self.source}/{self.board}"

    def url(self) -> str:
        raise NotImplementedError

    def parse(self, payload: Any) -> list[Job]:
        raise NotImplementedError

    def fetch(self) -> list[Job]:
        return self.parse(self._get(self.url()))

    def describe(self, jobs: list[Job]) -> list[Job]:
        """Fill in the ad text where the listing left it out. Most boards include it already."""
        return jobs

    def describe_each(self, jobs: list[Job], read: Callable[[Job], bool]) -> list[Job]:
        """Run `read` on several jobs at once and keep the ones it could read."""
        with ThreadPoolExecutor(max_workers=8) as pool:
            done = list(pool.map(read, jobs))
        return [job for job, ok in zip(jobs, done, strict=True) if ok]
