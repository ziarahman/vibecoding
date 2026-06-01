"""
schemas.py
==========
Core Pydantic schemas that govern the entire IPO-signal pipeline.

These models do double duty:

1. They enforce *strict, structured* output from every LLM node in the
   LangGraph pipeline (extraction + adjudication). The LLM is bound to these
   schemas via `with_structured_output`, so a malformed completion raises
   instead of silently corrupting the data store.

2. They define the public REST contract returned by the FastAPI layer.

Nothing in here imports SQLAlchemy or FastAPI — keep this module a pure,
dependency-light description of "what an IPO signal is".
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class VeracityStatus(str, Enum):
    """The adjudicated truth-state of a signal."""

    VERIFIED = "VERIFIED"          # corroborated by a primary/official source
    SPECULATIVE = "SPECULATIVE"    # plausible but unconfirmed ("noise")
    CONTRADICTED = "CONTRADICTED"  # disproven by a reliable source ("false")
    PENDING = "PENDING"            # discovered but not yet through the pipeline


class SignalCategory(str, Enum):
    """The kind of corporate event the signal describes."""

    S1_FILING = "S1_FILING"
    PRICE_RANGE = "PRICE_RANGE"
    ROADSHOW = "ROADSHOW"
    PRICING = "PRICING"
    LISTING = "LISTING"
    WITHDRAWAL = "WITHDRAWAL"
    RUMOR = "RUMOR"
    OTHER = "OTHER"


# --------------------------------------------------------------------------- #
# Node 1 — Discovery output
# --------------------------------------------------------------------------- #
class DiscoveredDocument(BaseModel):
    """A raw candidate document surfaced by the Discovery node."""

    title: str = Field(..., description="Headline or document title.")
    url: str = Field(..., description="Canonical URL of the source document.")
    source: str = Field(..., description="Publisher / feed name, e.g. 'SEC EDGAR'.")
    snippet: str = Field("", description="Short text excerpt used for extraction.")
    published_at: Optional[datetime] = Field(
        None, description="Publication timestamp if the source exposes one."
    )

    @field_validator("title", "snippet")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


# --------------------------------------------------------------------------- #
# Node 2 — Extraction output  (LLM-structured)
# --------------------------------------------------------------------------- #
class ExtractedClaim(BaseModel):
    """
    A normalized, structured IPO claim parsed out of a discovered document.

    This is the schema the *Extraction* LLM node is forced to emit. Keep the
    field descriptions sharp — they are injected into the model as the tool /
    function schema and materially affect extraction quality.
    """

    company_name: str = Field(
        ..., description="Legal or commonly-used name of the company going public."
    )
    ticker: Optional[str] = Field(
        None, description="Proposed stock ticker symbol, uppercase, if stated."
    )
    exchange: Optional[str] = Field(
        None, description="Target listing exchange, e.g. 'NASDAQ' or 'NYSE'."
    )
    category: SignalCategory = Field(
        SignalCategory.OTHER,
        description="The IPO lifecycle event this claim represents.",
    )
    valuation_usd: Optional[float] = Field(
        None,
        description="Implied or stated valuation in US dollars (absolute, not millions).",
    )
    price_range_low: Optional[float] = Field(
        None, description="Low end of the per-share price range, in USD."
    )
    price_range_high: Optional[float] = Field(
        None, description="High end of the per-share price range, in USD."
    )
    shares_offered: Optional[float] = Field(
        None, description="Number of shares offered, if disclosed."
    )
    projected_date: Optional[str] = Field(
        None,
        description="Projected IPO / listing date as an ISO-8601 date string, "
        "or a coarse phrase like 'Q3 2026' if only that is known.",
    )
    headline_claim: str = Field(
        ...,
        description="One-sentence summary of the single most important assertion.",
    )
    raw_quote: Optional[str] = Field(
        None,
        description="Verbatim sentence from the source that grounds the claim.",
    )

    @field_validator("ticker")
    @classmethod
    def _upper_ticker(cls, v: Optional[str]) -> Optional[str]:
        return v.upper().strip() if v else v


# --------------------------------------------------------------------------- #
# Node 3 — Verification output
# --------------------------------------------------------------------------- #
class EvidenceItem(BaseModel):
    """A single corroborating or contradicting piece of evidence."""

    source: str = Field(..., description="Where the evidence came from.")
    url: Optional[str] = Field(None, description="Direct link to the evidence.")
    summary: str = Field(..., description="What this source says about the claim.")
    supports_claim: bool = Field(
        ..., description="True if it corroborates, False if it contradicts."
    )
    is_primary_source: bool = Field(
        False,
        description="True for official/primary sources (SEC filings, company PR).",
    )
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)


# --------------------------------------------------------------------------- #
# Node 4 — Adjudication output  (LLM-structured)
# --------------------------------------------------------------------------- #
class AdjudicationResult(BaseModel):
    """
    The adversarial "truth judge" verdict. This is the schema the *Adjudication*
    LLM node is forced to emit.
    """

    status: VeracityStatus = Field(
        ..., description="Final truth-state for the signal."
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Calibrated confidence in the verdict, 0.0–1.0.",
    )
    reasoning: str = Field(
        ...,
        description="Concise, evidence-grounded explanation for the verdict. "
        "Must reference the specific evidence that drove the decision.",
    )
    key_supporting_points: List[str] = Field(
        default_factory=list,
        description="Bullet points of evidence supporting the claim.",
    )
    key_contradicting_points: List[str] = Field(
        default_factory=list,
        description="Bullet points of evidence undermining the claim.",
    )

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v):
        # The PENDING state is internal-only; an LLM must never return it.
        if isinstance(v, str) and v.upper() == "PENDING":
            return VeracityStatus.SPECULATIVE
        return v


# --------------------------------------------------------------------------- #
# REST API read/response models
# --------------------------------------------------------------------------- #
class SignalRead(BaseModel):
    """The fully-hydrated signal returned by `GET /api/signals`."""

    id: int
    company_name: str
    ticker: Optional[str] = None
    exchange: Optional[str] = None
    category: SignalCategory
    status: VeracityStatus
    confidence: float

    valuation_usd: Optional[float] = None
    price_range_low: Optional[float] = None
    price_range_high: Optional[float] = None
    shares_offered: Optional[float] = None
    projected_date: Optional[str] = None

    headline_claim: str
    raw_quote: Optional[str] = None

    source_title: Optional[str] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None

    reasoning: Optional[str] = None
    key_supporting_points: List[str] = Field(default_factory=list)
    key_contradicting_points: List[str] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)

    discovered_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedSignals(BaseModel):
    """Envelope for a paginated, filtered list of signals."""

    items: List[SignalRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class StatsSummary(BaseModel):
    """Aggregate counts powering the dashboard stat cards."""

    total_tracked: int
    verified: int
    speculative: int
    contradicted: int
    pending: int
    last_scan_at: Optional[datetime] = None


class ScanResult(BaseModel):
    """Response from `POST /api/signals/scan`."""

    status: str
    documents_discovered: int
    claims_extracted: int
    signals_upserted: int
    duration_seconds: float
    detail: Optional[str] = None
