from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

SPONSORSHIP_OFFERED = "offered"
SPONSORSHIP_UNCLEAR = "unclear"
SPONSORSHIP_UNKNOWN = "not mentioned"
SPONSORSHIP_EXCLUDED = "excluded"


@dataclass
class Job:
    source: str
    board: str
    company: str
    job_id: str
    title: str
    url: str
    locations: list[str] = field(default_factory=list)
    remote: bool | None = None
    description: str = ""
    published_at: datetime | None = None
    sponsorship: str = SPONSORSHIP_UNKNOWN
    flags: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Key for the seen store: source, board and job id."""
        return f"{self.source}:{self.board}:{self.job_id}".lower()
