"""
Gemini implementation of LLMProvider, using the current official `google-genai`
SDK (the deprecated `google-generativeai` package is no longer a dependency).
"""

from __future__ import annotations

import logging
import time
from typing import Iterator, Optional

from google import genai

from .base import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        t0 = time.perf_counter()
        logger.info("llm_call start provider=gemini model=%s", self._model)
        response = self._client.models.generate_content(model=self._model, contents=contents)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        logger.info("llm_call done provider=gemini model=%s elapsed_ms=%s", self._model, elapsed_ms)
        return response.text

    def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        for chunk in self._client.models.generate_content_stream(model=self._model, contents=contents):
            if chunk.text:
                yield chunk.text
