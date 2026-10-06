from __future__ import annotations

import datetime as dt
from urllib.parse import urlparse

import feedparser
import httpx

from app.config import REQUEST_TIMEOUT_SECONDS, USER_AGENT, Source
from app.fetchers import FetchedItem


def _matches(entry, source: Source) -> bool:
    if not source.include_path_prefixes and not source.include_categories:
        return True

    link = entry.get("link", "")
    path = urlparse(link).path
    if any(path.startswith(prefix) for prefix in source.include_path_prefixes):
        return True

    categories = {tag.get("term", "") for tag in entry.get("tags", [])}
    if any(cat in categories for cat in source.include_categories):
        return True

    return False


def fetch(source: Source) -> list[FetchedItem]:
    if not source.feed_url:
        raise ValueError("feed_url が未入力です")
    resp = httpx.get(
        source.feed_url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)

    items: list[FetchedItem] = []
    for entry in parsed.entries:
        if not _matches(entry, source):
            continue

        published_at = None
        if getattr(entry, "published_parsed", None):
            published_at = dt.datetime(*entry.published_parsed[:6], tzinfo=dt.timezone.utc)

        image_url = None
        if getattr(entry, "media_content", None):
            image_url = entry.media_content[0].get("url")
        elif "image" in entry:
            image_url = entry.get("image", {}).get("href")

        items.append(
            FetchedItem(
                title=entry.get("title", "(no title)"),
                link=entry.get("link"),
                summary=entry.get("summary"),
                image_url=image_url,
                published_at=published_at,
            )
        )
    return items
