"""
agents.py
=========
The multi-agent IPO-signal pipeline, modeled as a LangGraph `StateGraph`.

    Discovery  ->  Extraction  ->  Verification  ->  Adjudication

Each node is a pure function of the shared `PipelineState`. The graph is
compiled once and reused. Every node is defensive: if the LLM or a network
source is unavailable, it falls back to deterministic heuristics so the whole
pipeline runs end-to-end in a zero-credential demo.

Design notes
------------
* Discovery pulls from RSS feeds (SEC EDGAR S-1 atom, Nasdaq IPO feed) and,
  if configured, Tavily web search. A small synthetic seed guarantees the
  demo always has data.
* Extraction binds the LLM to `ExtractedClaim` (strict Pydantic).
* Verification queries SEC EDGAR full-text search + a consensus web search,
  producing an `EvidenceItem` audit trail.
* Adjudication is an adversarial "truth judge" bound to `AdjudicationResult`.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List, Optional, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph

from config import settings
from llm import get_structured_llm, llm_available
from schemas import (
    AdjudicationResult,
    DiscoveredDocument,
    EvidenceItem,
    ExtractedClaim,
    SignalCategory,
    VeracityStatus,
)

logger = logging.getLogger("ipo.agents")

_HTTP_HEADERS = {"User-Agent": settings.http_user_agent}


# --------------------------------------------------------------------------- #
# Shared graph state
# --------------------------------------------------------------------------- #
class PipelineState(TypedDict, total=False):
    """State threaded through every node of the graph."""

    documents: List[DiscoveredDocument]
    claims: List[ExtractedClaim]
    evidence_map: dict          # index -> List[EvidenceItem]
    verdicts: List[AdjudicationResult]
    # Final, joined records ready to persist.
    results: List[dict]
    errors: List[str]


# --------------------------------------------------------------------------- #
# Synthetic seed (keeps the demo populated with no network/keys)
# --------------------------------------------------------------------------- #
_SEED_DOCUMENTS: List[DiscoveredDocument] = [
    DiscoveredDocument(
        title="Helion Dynamics files Form S-1 for proposed IPO on Nasdaq",
        url="https://www.sec.gov/cgi-bin/browse-edgar?company=helion-dynamics",
        source="SEC EDGAR",
        snippet=(
            "Helion Dynamics, Inc. filed a Form S-1 registration statement with the "
            "SEC for a proposed initial public offering. The company intends to list "
            "its common stock on the Nasdaq Global Market under the ticker 'HLDX'. "
            "The filing indicates an anticipated price range of $18.00 to $21.00 per "
            "share with an expected valuation of approximately $4.2 billion, targeting "
            "Q3 2026."
        ),
        published_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    ),
    DiscoveredDocument(
        title="Sources: Northwind Robotics weighing a 2026 public listing",
        url="https://example-news.com/northwind-robotics-ipo-rumor",
        source="MarketChatter",
        snippet=(
            "According to people familiar with the matter, Northwind Robotics is "
            "exploring a potential IPO that could value the autonomous-logistics "
            "startup at over $9 billion. No registration statement has been filed and "
            "the company declined to comment. A listing on the NYSE has been floated "
            "for late 2026."
        ),
        published_at=datetime(2026, 5, 30, tzinfo=timezone.utc),
    ),
    DiscoveredDocument(
        title="Aurora Bioworks denies report of imminent IPO pricing",
        url="https://example-news.com/aurora-bioworks-denial",
        source="BioFinance Daily",
        snippet=(
            "Aurora Bioworks issued a statement denying a viral report that it had set "
            "IPO pricing at $30 per share for next week. 'We have no IPO scheduled and "
            "have not filed an S-1,' a spokesperson said, contradicting the earlier "
            "social-media claim of a $6 billion debut."
        ),
        published_at=datetime(2026, 5, 31, tzinfo=timezone.utc),
    ),
    DiscoveredDocument(
        title="Cobalt Cloud sets terms: 25M shares at $22-$24 ahead of NYSE debut",
        url="https://www.sec.gov/cgi-bin/browse-edgar?company=cobalt-cloud",
        source="SEC EDGAR",
        snippet=(
            "Cobalt Cloud Holdings announced the terms of its IPO, offering 25 million "
            "shares at an expected price range of $22.00 to $24.00 per share. At the "
            "midpoint the offering implies a valuation of roughly $5.8 billion. Shares "
            "are expected to begin trading on the NYSE under the symbol 'CBLT'."
        ),
        published_at=datetime(2026, 5, 29, tzinfo=timezone.utc),
    ),
]


# --------------------------------------------------------------------------- #
# Prompt templates
# --------------------------------------------------------------------------- #
EXTRACTION_SYSTEM_PROMPT = """\
You are a meticulous financial-data extraction agent specializing in IPO events.
Given a news headline and snippet, extract a single, structured IPO claim.

Rules:
- Only extract what is explicitly stated. Never invent figures.
- Convert valuations to absolute USD (e.g. "$4.2 billion" -> 4200000000).
- Classify the event into the correct lifecycle category.
- `headline_claim` must be ONE neutral sentence capturing the core assertion.
- If a field is not stated, leave it null.
- Quote the single most load-bearing sentence verbatim in `raw_quote`.
"""

ADJUDICATION_SYSTEM_PROMPT = """\
You are an adversarial truth-judge for IPO signals. You are deliberately
skeptical. Given a structured claim and a list of evidence items gathered from
verification sources, decide the claim's veracity.

Decision framework:
- VERIFIED: corroborated by at least one PRIMARY source (SEC filing, official
  company release) OR strong multi-source consensus, with no credible
  contradiction.
- CONTRADICTED: a reliable source explicitly disproves the claim, or an
  official source denies it.
- SPECULATIVE: plausible but unconfirmed — rumor, "sources say", single
  low-authority source, or no corroboration.

Calibrate `confidence` honestly (0.0–1.0). Ground `reasoning` in the specific
evidence. Populate supporting and contradicting points from the evidence only.
Never output PENDING.
"""


# --------------------------------------------------------------------------- #
# Node 1 — Discovery
# --------------------------------------------------------------------------- #
def _fetch_rss(url: str, limit: int) -> List[DiscoveredDocument]:
    docs: List[DiscoveredDocument] = []
    try:
        import feedparser

        resp = httpx.get(url, headers=_HTTP_HEADERS, timeout=12.0, follow_redirects=True)
        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:limit]:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            summary = re.sub(r"<[^>]+>", " ", getattr(entry, "summary", "")).strip()
            if not title or not link:
                continue
            published = None
            if getattr(entry, "published_parsed", None):
                try:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    published = None
            docs.append(
                DiscoveredDocument(
                    title=title,
                    url=link,
                    source=feed.feed.get("title", "RSS") if feed.feed else "RSS",
                    snippet=summary[:1200],
                    published_at=published,
                )
            )
    except Exception as exc:
        logger.info("RSS fetch failed for %s: %s", url, exc)
    return docs


def _fetch_tavily(limit: int) -> List[DiscoveredDocument]:
    if not settings.tavily_api_key:
        return []
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.tavily_api_key)
        res = client.search(
            query="upcoming IPO S-1 filing price range valuation listing",
            search_depth="basic",
            max_results=limit,
            topic="news",
        )
        docs = []
        for r in res.get("results", []):
            docs.append(
                DiscoveredDocument(
                    title=r.get("title", "Untitled"),
                    url=r.get("url", ""),
                    source="Tavily/Web",
                    snippet=(r.get("content") or "")[:1200],
                )
            )
        return docs
    except Exception as exc:
        logger.info("Tavily search failed: %s", exc)
        return []


def discovery_node(state: PipelineState) -> PipelineState:
    """Surface candidate IPO documents from RSS + web search (+ seed)."""
    limit = settings.discovery_max_documents
    docs: List[DiscoveredDocument] = []

    for feed_url in settings.rss_feed_list:
        docs.extend(_fetch_rss(feed_url, limit))
    docs.extend(_fetch_tavily(limit))

    # Always include the seed so the demo is never empty.
    docs.extend(_SEED_DOCUMENTS)

    # Dedup by URL, keep order, cap to limit.
    seen: set[str] = set()
    deduped: List[DiscoveredDocument] = []
    for d in docs:
        key = d.url or d.title
        if key in seen:
            continue
        seen.add(key)
        deduped.append(d)

    deduped = deduped[: max(limit, len(_SEED_DOCUMENTS))]
    logger.info("Discovery: %d candidate documents", len(deduped))
    return {"documents": deduped, "errors": state.get("errors", [])}


# --------------------------------------------------------------------------- #
# Node 2 — Extraction
# --------------------------------------------------------------------------- #
_BILLION = 1_000_000_000
_MILLION = 1_000_000


def _heuristic_extract(doc: DiscoveredDocument) -> Optional[ExtractedClaim]:
    """Regex/keyword extraction used when no LLM is available."""
    text = f"{doc.title}. {doc.snippet}"

    # Strip common news prefixes ("Sources:", "Exclusive:", "Report:") so the
    # company-name regex anchors on the actual subject of the headline.
    title_for_name = re.sub(
        r"^(Sources?|Exclusive|Report|Breaking|Update)\b[:,]?\s*",
        "",
        doc.title,
        flags=re.I,
    )

    # Company name: take leading proper-noun phrase from the cleaned title.
    m = re.match(r"([A-Z][\w&.\-]+(?:\s+[A-Z][\w&.\-]+){0,3})", title_for_name)
    company = m.group(1).strip() if m else title_for_name[:48]
    company = re.sub(
        r"\b(Sources?|Report|Inc|Corp|Holdings?)\b\.?$", "", company
    ).strip(" :,-")

    ticker = None
    tm = re.search(r"\b(?:ticker|symbol)\s*['\"]?([A-Z]{2,5})['\"]?", text, re.I)
    if tm:
        ticker = tm.group(1).upper()

    exchange = None
    if re.search(r"\bnasdaq\b", text, re.I):
        exchange = "NASDAQ"
    elif re.search(r"\bnyse\b", text, re.I):
        exchange = "NYSE"

    valuation = None
    vm = re.search(r"\$?\s*([\d.]+)\s*(billion|million)\b", text, re.I)
    if vm:
        val = float(vm.group(1))
        valuation = val * (_BILLION if vm.group(2).lower() == "billion" else _MILLION)

    low = high = None
    pm = re.search(r"\$\s*([\d.]+)\s*(?:to|-|–)\s*\$?\s*([\d.]+)", text)
    if pm:
        low, high = float(pm.group(1)), float(pm.group(2))

    shares = None
    sm = re.search(r"([\d.]+)\s*million\s+shares", text, re.I)
    if sm:
        shares = float(sm.group(1)) * _MILLION

    proj = None
    dm = re.search(r"\b(Q[1-4]\s*20\d{2}|20\d{2})\b", text)
    if dm:
        proj = dm.group(1)

    category = SignalCategory.OTHER
    low_text = text.lower()
    # Denials/withdrawals take precedence — they often *mention* an S-1 only to
    # refute it, so they must be detected before the filing branch.
    if any(w in low_text for w in ("deny", "denies", "denied", "denying", "no ipo", "withdraw")):
        category = SignalCategory.WITHDRAWAL
    elif "rumor" in low_text or "weighing" in low_text or "exploring" in low_text or "sources" in low_text:
        category = SignalCategory.RUMOR
    elif "s-1" in low_text or "registration statement" in low_text:
        category = SignalCategory.S1_FILING
    elif "price range" in low_text or "sets terms" in low_text or "per share" in low_text:
        category = SignalCategory.PRICE_RANGE
    elif "begin trading" in low_text or "debut" in low_text or "listing" in low_text:
        category = SignalCategory.LISTING

    if not company:
        return None

    return ExtractedClaim(
        company_name=company,
        ticker=ticker,
        exchange=exchange,
        category=category,
        valuation_usd=valuation,
        price_range_low=low,
        price_range_high=high,
        shares_offered=shares,
        projected_date=proj,
        headline_claim=doc.title.strip(),
        raw_quote=doc.snippet[:280] if doc.snippet else None,
    )


def extraction_node(state: PipelineState) -> PipelineState:
    """Parse each document into a strict `ExtractedClaim`."""
    structured = get_structured_llm(ExtractedClaim)
    claims: List[ExtractedClaim] = []
    errors = state.get("errors", [])

    for doc in state.get("documents", []):
        claim: Optional[ExtractedClaim] = None
        if structured is not None:
            try:
                prompt = (
                    f"{EXTRACTION_SYSTEM_PROMPT}\n\n"
                    f"TITLE: {doc.title}\n"
                    f"SOURCE: {doc.source}\n"
                    f"SNIPPET: {doc.snippet}"
                )
                claim = structured.invoke(prompt)  # type: ignore[assignment]
            except Exception as exc:
                logger.info("LLM extraction failed, falling back: %s", exc)
                errors.append(f"extract:{doc.url}:{exc}")
        if claim is None:
            claim = _heuristic_extract(doc)
        if claim is not None:
            claims.append(claim)
        else:
            # Keep alignment between documents and claims.
            claims.append(
                ExtractedClaim(
                    company_name=doc.title[:48] or "Unknown",
                    category=SignalCategory.OTHER,
                    headline_claim=doc.title,
                )
            )

    logger.info("Extraction: %d claims", len(claims))
    return {"claims": claims, "errors": errors}


# --------------------------------------------------------------------------- #
# Node 3 — Verification
# --------------------------------------------------------------------------- #
def _sec_edgar_lookup(company: str) -> Optional[EvidenceItem]:
    """Query SEC EDGAR full-text search for a corroborating filing."""
    try:
        q = httpx.get(
            "https://efts.sec.gov/LATEST/search-index",
            params={"q": f'"{company}"', "forms": "S-1"},
            headers=_HTTP_HEADERS,
            timeout=10.0,
        )
        if q.status_code == 200:
            data = q.json()
            hits = data.get("hits", {}).get("hits", [])
            if hits:
                top = hits[0]
                cik = top.get("_source", {}).get("cik", "")
                adsh = top.get("_id", "")
                url = (
                    f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
                    if cik
                    else "https://www.sec.gov/cgi-bin/browse-edgar"
                )
                return EvidenceItem(
                    source="SEC EDGAR Full-Text Search",
                    url=url,
                    summary=f"Found {len(hits)} S-1-related filing(s) matching '{company}' (accession {adsh}).",
                    supports_claim=True,
                    is_primary_source=True,
                )
    except Exception as exc:
        logger.info("SEC EDGAR lookup failed for %s: %s", company, exc)
    return None


def _consensus_search(claim: ExtractedClaim) -> List[EvidenceItem]:
    """Use Tavily (if configured) as a consensus / corroboration check."""
    if not settings.tavily_api_key:
        return []
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.tavily_api_key)
        res = client.search(
            query=f"{claim.company_name} IPO {claim.category.value}",
            search_depth="basic",
            max_results=3,
            topic="news",
        )
        items: List[EvidenceItem] = []
        for r in res.get("results", []):
            content = (r.get("content") or "").lower()
            contradicts = any(
                w in content for w in ("denies", "denied", "denying", "no ipo", "not filed", "false")
            )
            items.append(
                EvidenceItem(
                    source=r.get("title", "Web source"),
                    url=r.get("url"),
                    summary=(r.get("content") or "")[:240],
                    supports_claim=not contradicts,
                    is_primary_source=False,
                )
            )
        return items
    except Exception as exc:
        logger.info("Consensus search failed: %s", exc)
        return []


def _heuristic_evidence(doc: DiscoveredDocument, claim: ExtractedClaim) -> List[EvidenceItem]:
    """Build an evidence item from the originating document itself."""
    is_primary = "sec" in (doc.source or "").lower() or "edgar" in (doc.url or "").lower()
    text = f"{doc.title} {doc.snippet}".lower()
    contradicts = any(
        w in text
        for w in ("denies", "denied", "denying", "no ipo", "not filed", "no registration")
    )
    return [
        EvidenceItem(
            source=doc.source or "Originating document",
            url=doc.url,
            summary=doc.snippet[:240] or doc.title,
            supports_claim=not contradicts,
            is_primary_source=is_primary,
        )
    ]


def verification_node(state: PipelineState) -> PipelineState:
    """Gather an evidence audit trail for each claim."""
    documents = state.get("documents", [])
    claims = state.get("claims", [])
    evidence_map: dict = {}

    for idx, claim in enumerate(claims):
        evidence: List[EvidenceItem] = []
        doc = documents[idx] if idx < len(documents) else None
        if doc is not None:
            evidence.extend(_heuristic_evidence(doc, claim))

        sec_item = _sec_edgar_lookup(claim.company_name)
        if sec_item is not None:
            evidence.append(sec_item)

        evidence.extend(_consensus_search(claim))
        evidence_map[idx] = evidence

    logger.info("Verification: built audit trails for %d claims", len(claims))
    return {"evidence_map": evidence_map}


# --------------------------------------------------------------------------- #
# Node 4 — Adjudication
# --------------------------------------------------------------------------- #
def _heuristic_adjudicate(
    claim: ExtractedClaim, evidence: List[EvidenceItem]
) -> AdjudicationResult:
    """Deterministic truth-judge used when no LLM is available."""
    supporting = [e for e in evidence if e.supports_claim]
    contradicting = [e for e in evidence if not e.supports_claim]
    has_primary = any(e.is_primary_source and e.supports_claim for e in evidence)
    primary_denial = any(e.is_primary_source and not e.supports_claim for e in evidence)

    if contradicting and (primary_denial or claim.category == SignalCategory.WITHDRAWAL):
        status = VeracityStatus.CONTRADICTED
        confidence = 0.82
        reasoning = (
            "A reliable source explicitly disproves or denies the claim, so it is "
            "judged false. The contradiction outweighs any unverified assertion."
        )
    elif has_primary:
        status = VeracityStatus.VERIFIED
        confidence = 0.9 if len(supporting) > 1 else 0.78
        reasoning = (
            "The claim is corroborated by a primary source (e.g. an SEC filing or "
            "official terms), with no credible contradiction in the gathered evidence."
        )
    elif claim.category == SignalCategory.RUMOR or not supporting:
        status = VeracityStatus.SPECULATIVE
        confidence = 0.5
        reasoning = (
            "The claim rests on unattributed or single-source reporting with no "
            "primary corroboration, so it is treated as speculative noise."
        )
    else:
        status = VeracityStatus.SPECULATIVE
        confidence = 0.6
        reasoning = (
            "Some secondary corroboration exists, but without a primary source the "
            "claim cannot be promoted to verified."
        )

    return AdjudicationResult(
        status=status,
        confidence=confidence,
        reasoning=reasoning,
        key_supporting_points=[e.summary[:160] for e in supporting][:4],
        key_contradicting_points=[e.summary[:160] for e in contradicting][:4],
    )


def _format_evidence(evidence: List[EvidenceItem]) -> str:
    lines = []
    for i, e in enumerate(evidence, 1):
        tag = "PRIMARY" if e.is_primary_source else "secondary"
        stance = "SUPPORTS" if e.supports_claim else "CONTRADICTS"
        lines.append(f"[{i}] ({tag}, {stance}) {e.source}: {e.summary}")
    return "\n".join(lines) if lines else "(no evidence gathered)"


def adjudication_node(state: PipelineState) -> PipelineState:
    """Render a final, adversarial verdict per claim and join everything."""
    claims = state.get("claims", [])
    documents = state.get("documents", [])
    evidence_map = state.get("evidence_map", {})
    structured = get_structured_llm(AdjudicationResult)

    results: List[dict] = []
    for idx, claim in enumerate(claims):
        evidence = evidence_map.get(idx, [])
        verdict: Optional[AdjudicationResult] = None

        if structured is not None:
            try:
                prompt = (
                    f"{ADJUDICATION_SYSTEM_PROMPT}\n\n"
                    f"CLAIM:\n{claim.model_dump_json(indent=2)}\n\n"
                    f"EVIDENCE:\n{_format_evidence(evidence)}"
                )
                verdict = structured.invoke(prompt)  # type: ignore[assignment]
            except Exception as exc:
                logger.info("LLM adjudication failed, falling back: %s", exc)
        if verdict is None:
            verdict = _heuristic_adjudicate(claim, evidence)

        doc = documents[idx] if idx < len(documents) else None
        results.append(
            {
                "claim": claim,
                "verdict": verdict,
                "evidence": evidence,
                "document": doc,
            }
        )

    logger.info("Adjudication: %d verdicts rendered", len(results))
    return {"results": results}


# --------------------------------------------------------------------------- #
# Graph assembly
# --------------------------------------------------------------------------- #
def build_graph():
    """Compile the 4-node StateGraph."""
    graph = StateGraph(PipelineState)
    graph.add_node("discovery", discovery_node)
    graph.add_node("extraction", extraction_node)
    graph.add_node("verification", verification_node)
    graph.add_node("adjudication", adjudication_node)

    graph.add_edge(START, "discovery")
    graph.add_edge("discovery", "extraction")
    graph.add_edge("extraction", "verification")
    graph.add_edge("verification", "adjudication")
    graph.add_edge("adjudication", END)

    return graph.compile()


# Compile once at import time.
PIPELINE = build_graph()


def run_pipeline() -> List[dict]:
    """
    Execute the full pipeline and return the joined result records.

    Each record is a dict with keys: claim, verdict, evidence, document.
    """
    logger.info("Running IPO signal pipeline (llm_available=%s)", llm_available())
    final_state: PipelineState = PIPELINE.invoke({"errors": []})
    return final_state.get("results", [])
