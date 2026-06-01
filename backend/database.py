"""
database.py
===========
SQLAlchemy ORM layer.

Defines the `Signal` table that historicalizes every discovered IPO signal,
plus the engine/session plumbing. Uses a JSON column for the evidence + the
adjudication bullet lists so the audit trail survives round-trips without a
second table, while keeping the queryable scalar fields first-class columns.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, List

from sqlalchemy import (
    Float,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)
from sqlalchemy.types import TypeDecorator

from config import settings


# --------------------------------------------------------------------------- #
# Engine + session factory
# --------------------------------------------------------------------------- #
_connect_args: dict[str, Any] = {}
if settings.database_url.startswith("sqlite"):
    # SQLite + threaded FastAPI requires this flag.
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
)


# --------------------------------------------------------------------------- #
# Portable JSON column (works on both SQLite and Postgres)
# --------------------------------------------------------------------------- #
class JSONEncodedList(TypeDecorator):
    """Stores a Python list/dict as a JSON-encoded TEXT column."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> str:
        return json.dumps(value if value is not None else [])

    def process_result_value(self, value: str | None, dialect) -> Any:
        if value is None or value == "":
            return []
        return json.loads(value)


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- #
# Signal table
# --------------------------------------------------------------------------- #
class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Identity / dedup key
    company_name: Mapped[str] = mapped_column(String(256), index=True)
    ticker: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    exchange: Mapped[str | None] = mapped_column(String(32), nullable=True)
    category: Mapped[str] = mapped_column(String(32), default="OTHER", index=True)

    # Extracted metrics
    valuation_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_range_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_range_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares_offered: Mapped[float | None] = mapped_column(Float, nullable=True)
    projected_date: Mapped[str | None] = mapped_column(String(64), nullable=True)

    headline_claim: Mapped[str] = mapped_column(Text, default="")
    raw_quote: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Source provenance
    source_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    source_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Adjudication
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_supporting_points: Mapped[List[str]] = mapped_column(
        JSONEncodedList, default=list
    )
    key_contradicting_points: Mapped[List[str]] = mapped_column(
        JSONEncodedList, default=list
    )

    # Verification audit trail (list of EvidenceItem dicts)
    evidence: Mapped[List[dict]] = mapped_column(JSONEncodedList, default=list)

    # Timestamps
    discovered_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )


def init_db() -> None:
    """Create all tables. Idempotent — safe to call on every startup."""
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    """Return a new session. Caller is responsible for closing it."""
    return SessionLocal()
