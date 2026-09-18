from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import Source
from app.db import SessionLocal
from app.fetchers import html_listing, rss_link_filter
from app.models import Article, SourceStatus
from app.sources_store import list_enabled_sources
from app.summarize import summarize_article

logger = logging.getLogger("customrss.aggregator")


def _known_links_for(session, source_name: str) -> set[str]:
    rows = session.execute(
        select(Article.link).where(Article.source_name == source_name)
    ).scalars()
    return set(rows)


def fetch_source(source: Source) -> int:
    """1つのソースを取得しDBへ反映する。戻り値は新規追加件数。"""
    session = SessionLocal()
    new_count = 0
    try:
        known_links = _known_links_for(session, source.name)

        if source.type == "rss_link_filter":
            items = rss_link_filter.fetch(source)
        elif source.type == "html_listing":
            items = html_listing.fetch(source, known_links=known_links)
        else:
            raise ValueError(f"unknown source type: {source.type}")

        for item in items:
            if item.link in known_links:
                continue
            article = Article(
                source_name=source.name,
                title=item.title,
                link=item.link,
                summary=item.summary,
                image_url=item.image_url,
                published_at=item.published_at,
            )
            session.add(article)
            try:
                session.flush()
                known_links.add(item.link)
                new_count += 1
            except IntegrityError:
                # 同時実行や既知重複による衝突は無視する
                session.rollback()
                continue

            try:
                sentences = summarize_article(item.link, source.content_selector)
                article.key_sentences = "\n".join(sentences) if sentences else None
            except Exception:  # noqa: BLE001
                logger.exception("failed to summarize %s", item.link)

        status = session.get(SourceStatus, source.name)
        if status is None:
            status = SourceStatus(name=source.name)
            session.add(status)
        now = dt.datetime.now(dt.timezone.utc)
        status.last_run_at = now
        status.last_success_at = now
        status.last_error = None
        status.new_items_last_run = new_count

        session.commit()
        logger.info("fetched %s: %d new item(s)", source.name, new_count)
        return new_count
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        status = session.get(SourceStatus, source.name)
        if status is None:
            status = SourceStatus(name=source.name)
            session.add(status)
        status.last_run_at = dt.datetime.now(dt.timezone.utc)
        status.last_error = str(exc)
        session.commit()
        logger.exception("failed to fetch %s", source.name)
        return 0
    finally:
        session.close()


def test_fetch(source: Source, limit: int = 5) -> tuple[list, int]:
    """DBに書き込まずに取得だけ試す(ソース設定フォームの「テスト取得」用)。"""
    if source.type == "rss_link_filter":
        items = rss_link_filter.fetch(source)
    elif source.type == "html_listing":
        items = html_listing.fetch(source, known_links=set())
    else:
        raise ValueError(f"unknown source type: {source.type}")
    return items[:limit], len(items)


def fetch_all() -> dict[str, int]:
    session = SessionLocal()
    try:
        sources = list_enabled_sources(session)
    finally:
        session.close()

    results: dict[str, int] = {}
    for source in sources:
        results[source.name] = fetch_source(source)
    return results
