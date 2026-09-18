from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Selectors, Source
from app.models import SourceConfig


def _lines(text: str | None) -> list[str]:
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def to_source(row: SourceConfig) -> Source:
    selectors = None
    if row.type == "html_listing":
        selectors = Selectors(
            item=row.selector_item or "",
            link=row.selector_link or "",
            title=row.selector_title or "",
            date=row.selector_date,
            date_format=row.selector_date_format,
            summary=row.selector_summary,
            image=row.selector_image,
        )
    return Source(
        name=row.name,
        type=row.type,
        enabled=row.enabled,
        base_url=row.base_url,
        feed_url=row.feed_url,
        include_path_prefixes=_lines(row.include_path_prefixes),
        include_categories=_lines(row.include_categories),
        list_url_template=row.list_url_template,
        max_pages=row.max_pages,
        stop_when_no_new_items=row.stop_when_no_new_items,
        selectors=selectors,
        content_selector=row.content_selector,
    )


def list_sources(session: Session) -> list[SourceConfig]:
    return list(session.execute(select(SourceConfig).order_by(SourceConfig.name)).scalars())


def list_enabled_sources(session: Session) -> list[Source]:
    rows = session.execute(select(SourceConfig).where(SourceConfig.enabled.is_(True)))
    return [to_source(row) for row in rows.scalars()]


def get_source(session: Session, name: str) -> SourceConfig | None:
    return session.get(SourceConfig, name)


def apply_form(row: SourceConfig, form: dict) -> None:
    row.type = form["type"]
    row.enabled = form.get("enabled") == "on"
    row.base_url = form.get("base_url", "").strip()
    row.feed_url = form.get("feed_url", "").strip() or None
    row.include_path_prefixes = form.get("include_path_prefixes", "").strip() or None
    row.include_categories = form.get("include_categories", "").strip() or None
    row.list_url_template = form.get("list_url_template", "").strip() or None
    row.max_pages = int(form.get("max_pages") or 1)
    row.stop_when_no_new_items = form.get("stop_when_no_new_items") == "on"
    row.selector_item = form.get("selector_item", "").strip() or None
    row.selector_link = form.get("selector_link", "").strip() or None
    row.selector_title = form.get("selector_title", "").strip() or None
    row.selector_date = form.get("selector_date", "").strip() or None
    row.selector_date_format = form.get("selector_date_format", "").strip() or None
    row.selector_summary = form.get("selector_summary", "").strip() or None
    row.selector_image = form.get("selector_image", "").strip() or None
    row.content_selector = form.get("content_selector", "").strip() or None


def source_from_form(name: str, form: dict) -> Source:
    """フォーム入力から(DBに保存せず)Sourceを組み立てる。テスト取得用。"""
    row = SourceConfig(name=name)
    apply_form(row, form)
    return to_source(row)


def create_source(session: Session, name: str, form: dict) -> SourceConfig:
    row = SourceConfig(name=name)
    apply_form(row, form)
    session.add(row)
    return row


def delete_source(session: Session, name: str) -> None:
    row = session.get(SourceConfig, name)
    if row is not None:
        session.delete(row)
