from __future__ import annotations

import datetime as dt
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.config import REQUEST_TIMEOUT_SECONDS, USER_AGENT, Source
from app.fetchers import FetchedItem


def _text(node, selector: str) -> str | None:
    el = node.select_one(selector)
    if el is None:
        return None
    return el.get_text(strip=True)


def _attr(node, selector: str, attr: str) -> str | None:
    el = node.select_one(selector)
    if el is None:
        return None
    return el.get(attr)


def _parse_card(card, source: Source) -> FetchedItem | None:
    sel = source.selectors
    assert sel is not None

    href = _attr(card, sel.link, "href")
    if not href:
        return None
    link = urljoin(source.base_url, href)

    title = _text(card, sel.title) or "(no title)"

    published_at = None
    if sel.date:
        date_text = _text(card, sel.date)
        if date_text and sel.date_format:
            try:
                published_at = dt.datetime.strptime(date_text, sel.date_format).replace(
                    tzinfo=dt.timezone.utc
                )
            except ValueError:
                published_at = None

    summary = _text(card, sel.summary) if sel.summary else None

    image_url = None
    if sel.image:
        src = _attr(card, sel.image, "src")
        if src:
            image_url = urljoin(source.base_url, src)

    return FetchedItem(
        title=title,
        link=link,
        summary=summary,
        image_url=image_url,
        published_at=published_at,
    )


def fetch(source: Source, known_links: set[str] | None = None) -> list[FetchedItem]:
    if not source.list_url_template:
        raise ValueError("一覧ページURL(list_url_template)が未入力です")
    if source.selectors is None or not (source.selectors.item and source.selectors.link and source.selectors.title):
        raise ValueError("記事カード・リンク・タイトルのセレクタ(item / link / title)は必須です")
    known_links = known_links or set()

    items: list[FetchedItem] = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for page in range(source.max_pages):
            url = source.list_url_template.format(page=page)
            resp = client.get(url, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            cards = soup.select(source.selectors.item)
            if not cards:
                break

            page_items = [_parse_card(c, source) for c in cards]
            page_items = [i for i in page_items if i is not None]
            items.extend(page_items)

            if source.stop_when_no_new_items and known_links:
                if any(i.link in known_links for i in page_items):
                    break

    return items
