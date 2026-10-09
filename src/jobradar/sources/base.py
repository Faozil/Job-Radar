from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..http import get_json
from ..models import Job

Getter = Callable[[str], Any]


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
