"""
main.py
=======
FastAPI application wiring the LangGraph pipeline to a REST API + SQLite store.

Endpoints
---------
GET  /api/health            -> liveness + LLM provider info
GET  /api/stats             -> aggregate counts for the dashboard stat cards
GET  /api/signals           -> filtered, sorted, paginated signal list
GET  /api/signals/{id}      -> single hydrated signal
POST /api/signals/scan      -> run the discovery pipeline and upsert results

The scan can run synchronously (default) or be dispatched to a background
worker thread (`?background=true`) so the UI stays responsive.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from math import ceil
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents import run_pipeline
from config import settings
from database import Signal, SessionLocal, init_db
from llm import llm_available
from schemas import (
    PaginatedSignals,
    ScanResult,
    SignalRead,
    StatsSummary,
    VeracityStatus,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("ipo.api")

# Module-level scan coordination.
_scan_lock = threading.Lock()
_last_scan_at: Optional[datetime] = None


# --------------------------------------------------------------------------- #
# Lifespan
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info(
        "DB initialized. LLM provider=%s available=%s",
        settings.llm_provider,
        llm_available(),
    )
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Multi-agent IPO financial-signal intelligence pipeline.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# DB dependency
# --------------------------------------------------------------------------- #
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Serialization helper
# --------------------------------------------------------------------------- #
def _to_read(row: Signal) -> SignalRead:
    return SignalRead(
        id=row.id,
        company_name=row.company_name,
        ticker=row.ticker,
        exchange=row.exchange,
        category=row.category,
        status=row.status,
        confidence=row.confidence,
        valuation_usd=row.valuation_usd,
        price_range_low=row.price_range_low,
        price_range_high=row.price_range_high,
        shares_offered=row.shares_offered,
        projected_date=row.projected_date,
        headline_claim=row.headline_claim,
        raw_quote=row.raw_quote,
        source_title=row.source_title,
        source_url=row.source_url,
        source_name=row.source_name,
        reasoning=row.reasoning,
        key_supporting_points=row.key_supporting_points or [],
        key_contradicting_points=row.key_contradicting_points or [],
        evidence=row.evidence or [],
        discovered_at=row.discovered_at,
        updated_at=row.updated_at,
    )


# --------------------------------------------------------------------------- #
# Pipeline -> DB upsert
# --------------------------------------------------------------------------- #
def _persist_results(db: Session, results: List[dict]) -> int:
    """Upsert pipeline results by (company_name, source_url). Returns count."""
    upserted = 0
    for record in results:
        claim = record["claim"]
        verdict = record["verdict"]
        evidence = record["evidence"]
        doc = record.get("document")

        source_url = doc.url if doc else None
        evidence_payload = [
            e.model_dump(mode="json") if hasattr(e, "model_dump") else e
            for e in evidence
        ]

        # Dedup: same company + same source URL == same signal (update in place).
        existing = db.execute(
            select(Signal).where(
                Signal.company_name == claim.company_name,
                Signal.source_url == source_url,
            )
        ).scalar_one_or_none()

        target = existing or Signal(company_name=claim.company_name)

        target.company_name = claim.company_name
        target.ticker = claim.ticker
        target.exchange = claim.exchange
        target.category = claim.category.value
        target.valuation_usd = claim.valuation_usd
        target.price_range_low = claim.price_range_low
        target.price_range_high = claim.price_range_high
        target.shares_offered = claim.shares_offered
        target.projected_date = claim.projected_date
        target.headline_claim = claim.headline_claim
        target.raw_quote = claim.raw_quote

        target.source_title = doc.title if doc else None
        target.source_url = source_url
        target.source_name = doc.source if doc else None

        target.status = verdict.status.value
        target.confidence = verdict.confidence
        target.reasoning = verdict.reasoning
        target.key_supporting_points = verdict.key_supporting_points
        target.key_contradicting_points = verdict.key_contradicting_points
        target.evidence = evidence_payload

        if existing is None:
            db.add(target)
        upserted += 1

    db.commit()
    return upserted


def _execute_scan() -> ScanResult:
    """Run the pipeline + persist. Guarded by a lock to prevent overlap."""
    global _last_scan_at
    start = time.time()
    with _scan_lock:
        results = run_pipeline()
        db = SessionLocal()
        try:
            upserted = _persist_results(db, results)
        finally:
            db.close()
        _last_scan_at = datetime.utcnow()

    claims_extracted = len([r for r in results if r.get("claim")])
    return ScanResult(
        status="completed",
        documents_discovered=len(results),
        claims_extracted=claims_extracted,
        signals_upserted=upserted,
        duration_seconds=round(time.time() - start, 2),
        detail=f"LLM provider={settings.llm_provider} available={llm_available()}",
    )


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "llm_provider": settings.llm_provider,
        "llm_available": llm_available(),
        "last_scan_at": _last_scan_at,
    }


@app.get("/api/stats", response_model=StatsSummary)
def get_stats(db: Session = Depends(get_db)):
    counts = dict(
        db.execute(select(Signal.status, func.count(Signal.id)).group_by(Signal.status)).all()
    )
    total = sum(counts.values())
    return StatsSummary(
        total_tracked=total,
        verified=counts.get(VeracityStatus.VERIFIED.value, 0),
        speculative=counts.get(VeracityStatus.SPECULATIVE.value, 0),
        contradicted=counts.get(VeracityStatus.CONTRADICTED.value, 0),
        pending=counts.get(VeracityStatus.PENDING.value, 0),
        last_scan_at=_last_scan_at,
    )


@app.get("/api/signals", response_model=PaginatedSignals)
def list_signals(
    db: Session = Depends(get_db),
    status: Optional[VeracityStatus] = Query(None, description="Filter by veracity."),
    category: Optional[str] = Query(None, description="Filter by category."),
    search: Optional[str] = Query(None, description="Case-insensitive company/ticker match."),
    sort_by: str = Query("discovered_at", description="discovered_at|confidence|company_name"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    stmt = select(Signal)

    if status is not None:
        stmt = stmt.where(Signal.status == status.value)
    if category:
        stmt = stmt.where(Signal.category == category)
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            func.lower(Signal.company_name).like(like)
            | func.lower(func.coalesce(Signal.ticker, "")).like(like)
        )

    # Sorting (whitelist columns to avoid injection).
    sort_col = {
        "discovered_at": Signal.discovered_at,
        "confidence": Signal.confidence,
        "company_name": Signal.company_name,
        "updated_at": Signal.updated_at,
    }.get(sort_by, Signal.discovered_at)
    stmt = stmt.order_by(sort_col.asc() if sort_dir == "asc" else sort_col.desc())

    total = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()

    rows = (
        db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )

    return PaginatedSignals(
        items=[_to_read(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, ceil(total / page_size)) if total else 1,
    )


@app.get("/api/signals/{signal_id}", response_model=SignalRead)
def get_signal(signal_id: int, db: Session = Depends(get_db)):
    row = db.get(Signal, signal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    return _to_read(row)


@app.post("/api/signals/scan", response_model=ScanResult)
def trigger_scan(
    background: bool = Query(False, description="Dispatch scan to a worker thread."),
):
    """Manually trigger a discovery scan, synchronously or in the background."""
    if _scan_lock.locked():
        raise HTTPException(status_code=409, detail="A scan is already in progress.")

    if background:
        thread = threading.Thread(target=_execute_scan, daemon=True)
        thread.start()
        return ScanResult(
            status="dispatched",
            documents_discovered=0,
            claims_extracted=0,
            signals_upserted=0,
            duration_seconds=0.0,
            detail="Scan dispatched to background worker thread.",
        )

    return _execute_scan()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
