from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.aggregator import fetch_all
from app.config import FETCH_INTERVAL_MINUTES

logger = logging.getLogger("customrss.scheduler")

scheduler = BackgroundScheduler(timezone="UTC")


def _job() -> None:
    logger.info("scheduled fetch starting")
    fetch_all()


def start() -> None:
    # 初回起動時のフェッチは main.py から明示的に行う。
    # ここで登録するのは定期実行分(初回は interval 経過後)。
    scheduler.add_job(
        _job,
        "interval",
        minutes=FETCH_INTERVAL_MINUTES,
        id="fetch_all",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
