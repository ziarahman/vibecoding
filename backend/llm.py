"""
llm.py
======
Provider-agnostic LLM factory.

Lets the pipeline flip between a *local* Ollama model and *cloud* providers
(OpenAI, Anthropic) purely through environment variables — no code changes.

Every node that needs structured output calls `get_structured_llm(Schema)`,
which returns a runnable that is contractually bound to emit a valid instance
of the given Pydantic model.

The module degrades gracefully: if no provider is configured / reachable, the
agents fall back to deterministic heuristics so the app still runs end-to-end
in a zero-credentials demo environment.
"""

from __future__ import annotations

import logging
from typing import Optional, Type, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel

from config import settings

logger = logging.getLogger("ipo.llm")

T = TypeVar("T", bound=BaseModel)

_cached_llm: Optional[BaseChatModel] = None


def _build_llm() -> Optional[BaseChatModel]:
    """Instantiate the chat model for the configured provider, or None."""
    provider = settings.llm_provider.lower().strip()

    try:
        if provider == "openai":
            if not settings.openai_api_key:
                logger.warning("LLM_PROVIDER=openai but OPENAI_API_KEY is unset.")
                return None
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=settings.openai_model,
                api_key=settings.openai_api_key,
                temperature=settings.llm_temperature,
            )

        if provider == "anthropic":
            if not settings.anthropic_api_key:
                logger.warning(
                    "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is unset."
                )
                return None
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=settings.anthropic_model,
                api_key=settings.anthropic_api_key,
                temperature=settings.llm_temperature,
            )

        # Default: local Ollama
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=settings.llm_temperature,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to construct LLM (%s): %s", provider, exc)
        return None


def get_llm() -> Optional[BaseChatModel]:
    """Return a process-cached chat model instance (or None if unavailable)."""
    global _cached_llm
    if _cached_llm is None:
        _cached_llm = _build_llm()
    return _cached_llm


def get_structured_llm(schema: Type[T]):
    """
    Return a runnable bound to emit `schema`, or None if no LLM is configured.

    Callers MUST handle the None case with a heuristic fallback so the pipeline
    remains runnable without credentials.
    """
    llm = get_llm()
    if llm is None:
        return None
    try:
        return llm.with_structured_output(schema)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("with_structured_output unsupported: %s", exc)
        return None


def llm_available() -> bool:
    return get_llm() is not None
