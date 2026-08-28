"""
LLM provider registry.

get_provider() returns the configured LLMProvider, or None if unconfigured —
callers should handle None the same way chat.py always has (503 "not
configured"), not raise on import.
"""

import logging
import os
from typing import Optional

from .base import LLMProvider

logger = logging.getLogger(__name__)

__all__ = ["LLMProvider", "get_provider"]

_provider: Optional[LLMProvider] = None
_attempted = False


def get_provider() -> Optional[LLMProvider]:
    """
    Return the configured LLMProvider (cached after first call), or None if
    no provider is configured/available.

    Selection is via LLM_PROVIDER env var (default "gemini"). Only Gemini is
    implemented today — add more `elif` branches here as new providers are
    actually needed, each behind its own env var / API key.
    """
    global _provider, _attempted
    if _attempted:
        return _provider
    _attempted = True

    provider_name = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider_name == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("llm_provider not configured: GEMINI_API_KEY not set")
            return None
        try:
            from .gemini_provider import GeminiProvider

            _provider = GeminiProvider(api_key=api_key)
            logger.info("llm_provider ready provider=gemini")
        except Exception as e:
            logger.error("llm_provider init failed provider=gemini error=%s", e)
            _provider = None
    else:
        logger.warning("llm_provider unknown LLM_PROVIDER=%s", provider_name)

    return _provider
