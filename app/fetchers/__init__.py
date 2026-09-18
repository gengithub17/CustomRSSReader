from __future__ import annotations

from dataclasses import dataclass
import datetime as dt


@dataclass
class FetchedItem:
    title: str
    link: str
    summary: str | None = None
    image_url: str | None = None
    published_at: dt.datetime | None = None
