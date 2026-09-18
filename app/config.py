from __future__ import annotations

import os
from dataclasses import dataclass, field

DB_PATH = os.environ.get("DB_PATH", "/app/data/customrss.db")
FETCH_INTERVAL_MINUTES = int(os.environ.get("FETCH_INTERVAL_MINUTES", "30"))
USER_AGENT = os.environ.get(
    "CUSTOMRSS_USER_AGENT",
    "CustomRSSReader/1.0 (+https://github.com/gengithub17/CustomRSSReader)",
)
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "20"))


@dataclass
class Selectors:
    item: str
    link: str
    title: str
    date: str | None = None
    date_format: str | None = None
    summary: str | None = None
    image: str | None = None


@dataclass
class Source:
    name: str
    type: str
    enabled: bool = True
    base_url: str = ""

    # rss_link_filter
    feed_url: str | None = None
    include_path_prefixes: list[str] = field(default_factory=list)
    include_categories: list[str] = field(default_factory=list)

    # html_listing
    list_url_template: str | None = None
    max_pages: int = 1
    stop_when_no_new_items: bool = True
    selectors: Selectors | None = None

    # 記事本文抽出(重要文抜き出し用)。未指定時は汎用ヒューリスティックで代替する。
    content_selector: str | None = None
