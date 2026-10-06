from __future__ import annotations

import datetime as dt
import logging
import threading
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Query, Request
from pydantic import BaseModel
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update

from app import aggregator
from app.aggregator import fetch_all, running_sources, test_fetch
from app.db import SessionLocal, init_db
from app.models import Article, SourceStatus
from app.scheduler import start as start_scheduler
from app.sources_store import (
    apply_form as apply_source_form,
    create_source,
    delete_source,
    get_source,
    list_sources,
    source_from_form,
)

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="CustomRSSReader")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

JST = dt.timezone(dt.timedelta(hours=9))


def _jst(value: dt.datetime | None, fmt: str) -> str:
    """DBに保存されているUTC(naive)datetimeをJSTの文字列に変換する。"""
    if value is None:
        return "-"
    aware = value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(JST).strftime(fmt)


templates.env.filters["jst"] = _jst


def _apply_filters(stmt, sources: list[str], show: str, q: str | None, date_from: str | None, date_to: str | None):
    if sources:
        stmt = stmt.where(Article.source_name.in_(sources))
    if show == "unread":
        stmt = stmt.where(Article.is_read.is_(False))
    elif show == "read":
        stmt = stmt.where(Article.is_read.is_(True))
    elif show == "bookmarked":
        stmt = stmt.where(Article.is_bookmarked.is_(True))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            Article.title.ilike(like)
            | Article.summary.ilike(like)
            | Article.key_sentences.ilike(like)
        )
    if date_from:
        try:
            stmt = stmt.where(Article.published_at >= dt.datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            pass
    if date_to:
        try:
            until = dt.datetime.strptime(date_to, "%Y-%m-%d") + dt.timedelta(days=1)
            stmt = stmt.where(Article.published_at < until)
        except ValueError:
            pass
    return stmt


def _filters_query_string(sources: list[str], show: str, q: str, date_from: str, date_to: str) -> str:
    params = [("source", s) for s in sources]
    params.append(("show", show))
    if q:
        params.append(("q", q))
    if date_from:
        params.append(("date_from", date_from))
    if date_to:
        params.append(("date_to", date_to))
    return urlencode(params)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    start_scheduler()
    # 起動直後に1回だけ非同期でフェッチしておく(UIをすぐ埋めるため)
    threading.Thread(target=fetch_all, daemon=True).start()


@app.get("/")
def index(
    request: Request,
    source: list[str] = Query(default=[]),
    show: str = "unread",
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    if show not in ("unread", "read", "all", "bookmarked"):
        show = "unread"

    session = SessionLocal()
    try:
        query = select(Article).order_by(Article.published_at.desc().nullslast())
        query = _apply_filters(query, source, show, q, date_from, date_to)
        articles = session.execute(query.limit(200)).scalars().all()

        all_sources = sorted(
            {row[0] for row in session.execute(select(Article.source_name))}
        )
        unread_count = session.execute(
            select(Article).where(Article.is_read.is_(False))
        ).scalars().all()

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "articles": articles,
                "sources": all_sources,
                "current_sources": source,
                "show": show,
                "q": q or "",
                "date_from": date_from or "",
                "date_to": date_to or "",
                "unread_total": len(unread_count),
            },
        )
    finally:
        session.close()


@app.get("/read/{article_id}")
def read_article(article_id: int):
    session = SessionLocal()
    try:
        article = session.get(Article, article_id)
        if article is None:
            return RedirectResponse("/")
        article.is_read = True
        session.commit()
        return RedirectResponse(article.link)
    finally:
        session.close()


@app.post("/mark-read/{article_id}")
def mark_read(article_id: int):
    session = SessionLocal()
    try:
        session.execute(
            update(Article).where(Article.id == article_id).values(is_read=True)
        )
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@app.post("/mark-all-read")
async def mark_all_read(
    source: list[str] = Form(default=[]),
    show: str = Form(default="unread"),
    q: str = Form(default=""),
    date_from: str = Form(default=""),
    date_to: str = Form(default=""),
):
    session = SessionLocal()
    try:
        stmt = update(Article).values(is_read=True)
        stmt = _apply_filters(stmt, source, show, q, date_from, date_to)
        session.execute(stmt)
        session.commit()
        qs = _filters_query_string(source, show, q, date_from, date_to)
        return RedirectResponse(f"/?{qs}", status_code=303)
    finally:
        session.close()


class BulkMarkRequest(BaseModel):
    ids: list[int]
    read: bool


@app.post("/mark-bulk")
def mark_bulk(payload: BulkMarkRequest):
    if not payload.ids:
        return {"ok": True, "count": 0}
    session = SessionLocal()
    try:
        session.execute(
            update(Article).where(Article.id.in_(payload.ids)).values(is_read=payload.read)
        )
        session.commit()
        return {"ok": True, "count": len(payload.ids)}
    finally:
        session.close()


class BulkBookmarkRequest(BaseModel):
    ids: list[int]
    bookmarked: bool


@app.post("/bookmark-bulk")
def bookmark_bulk(payload: BulkBookmarkRequest):
    if not payload.ids:
        return {"ok": True, "count": 0}
    session = SessionLocal()
    try:
        session.execute(
            update(Article).where(Article.id.in_(payload.ids)).values(is_bookmarked=payload.bookmarked)
        )
        session.commit()
        return {"ok": True, "count": len(payload.ids)}
    finally:
        session.close()


@app.get("/sources")
def sources_status(request: Request):
    session = SessionLocal()
    try:
        configs = list_sources(session)
        statuses = {s.name: s for s in session.execute(select(SourceStatus)).scalars()}
        rows = [{"config": c, "status": statuses.get(c.name)} for c in configs]
        return templates.TemplateResponse(
            "sources.html",
            {
                "request": request,
                "rows": rows,
                "running": set(running_sources),
                "fetching": aggregator.active_fetch_runs > 0,
            },
        )
    finally:
        session.close()


@app.get("/sources/new")
def source_new_form(request: Request):
    return templates.TemplateResponse(
        "source_form.html", {"request": request, "row": None, "error": None}
    )


@app.post("/sources/new")
async def source_new_submit(request: Request):
    form = dict((await request.form()))
    name = (form.get("name") or "").strip()
    session = SessionLocal()
    try:
        if not name:
            return templates.TemplateResponse(
                "source_form.html",
                {"request": request, "row": None, "error": "ソース名は必須です。"},
            )
        if get_source(session, name) is not None:
            return templates.TemplateResponse(
                "source_form.html",
                {"request": request, "row": None, "error": f"「{name}」は既に存在します。"},
            )
        create_source(session, name, form)
        session.commit()
        return RedirectResponse("/sources", status_code=303)
    finally:
        session.close()


@app.get("/sources/{name}/edit")
def source_edit_form(request: Request, name: str):
    session = SessionLocal()
    try:
        row = get_source(session, name)
        if row is None:
            return RedirectResponse("/sources", status_code=303)
        return templates.TemplateResponse(
            "source_form.html", {"request": request, "row": row, "error": None}
        )
    finally:
        session.close()


@app.post("/sources/{name}/edit")
async def source_edit_submit(request: Request, name: str):
    form = dict((await request.form()))
    session = SessionLocal()
    try:
        row = get_source(session, name)
        if row is None:
            return RedirectResponse("/sources", status_code=303)
        apply_source_form(row, form)
        session.commit()
        return RedirectResponse("/sources", status_code=303)
    finally:
        session.close()


@app.post("/sources/{name}/delete")
def source_delete(name: str):
    session = SessionLocal()
    try:
        delete_source(session, name)
        session.commit()
        return RedirectResponse("/sources", status_code=303)
    finally:
        session.close()


@app.post("/sources/{name}/toggle")
def source_toggle(name: str):
    session = SessionLocal()
    try:
        row = get_source(session, name)
        if row is not None:
            row.enabled = not row.enabled
            session.commit()
        return RedirectResponse("/sources", status_code=303)
    finally:
        session.close()


@app.post("/sources/test")
async def source_test(request: Request):
    form = dict((await request.form()))
    name = form.get("name") or "(test)"
    try:
        source = source_from_form(name, form)
        sample, total = test_fetch(source, limit=5)
        return JSONResponse(
            {
                "ok": True,
                "total": total,
                "sample": [{"title": i.title, "link": i.link} for i in sample],
            }
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc) or type(exc).__name__})


@app.post("/fetch-now")
def fetch_now():
    threading.Thread(target=fetch_all, daemon=True).start()
    return RedirectResponse("/sources", status_code=303)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
