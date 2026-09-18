from __future__ import annotations

import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import DB_PATH
from app.models import Base

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# create_all()は既存テーブルへのカラム追加までは行わないため、
# 新しいカラムを追加した場合はここに (テーブル名, カラム定義) を追記する。
_COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("articles", "is_bookmarked", "BOOLEAN NOT NULL DEFAULT 0"),
]


def init_db() -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for table, column, ddl in _COLUMN_MIGRATIONS:
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if column not in existing:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN "{column}" {ddl}'))
