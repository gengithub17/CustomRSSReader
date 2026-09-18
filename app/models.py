from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, Integer, String, Text, Boolean, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (UniqueConstraint("link", name="uq_articles_link"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(1024))
    link: Mapped[str] = mapped_column(String(2048))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_bookmarked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # TextRankで抜き出した重要文。改行区切りで保存する(要約はAIエージェントを使わずサーバ側で完結)
    key_sentences: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceStatus(Base):
    __tablename__ = "source_status"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    last_run_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_items_last_run: Mapped[int] = mapped_column(Integer, default=0)


class SourceConfig(Base):
    """ユーザーがWeb UI(/sources)から追加・編集・削除するソース設定。"""

    __tablename__ = "source_config"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    type: Mapped[str] = mapped_column(String(32))  # rss_link_filter | html_listing
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    base_url: Mapped[str] = mapped_column(String(512), default="")

    # rss_link_filter
    feed_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    include_path_prefixes: Mapped[str | None] = mapped_column(Text, nullable=True)  # 改行区切り
    include_categories: Mapped[str | None] = mapped_column(Text, nullable=True)  # 改行区切り

    # html_listing
    list_url_template: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    max_pages: Mapped[int] = mapped_column(Integer, default=1)
    stop_when_no_new_items: Mapped[bool] = mapped_column(Boolean, default=True)
    selector_item: Mapped[str | None] = mapped_column(String(512), nullable=True)
    selector_link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    selector_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    selector_date: Mapped[str | None] = mapped_column(String(512), nullable=True)
    selector_date_format: Mapped[str | None] = mapped_column(String(64), nullable=True)
    selector_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    selector_image: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # 共通(要約用の本文抽出セレクタ)
    content_selector: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=lambda: dt.datetime.now(dt.timezone.utc)
    )
