"""
LLM provider interface.

The application depends on this interface, not on any vendor SDK directly.
Add a new provider by implementing LLMProvider and registering it in
get_provider() (see __init__.py) — nothing else in the codebase should need
to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, Optional


class LLMProvider(ABC):
    """Minimal interface every LLM backend must implement."""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Return a complete text response for *prompt*."""
        raise NotImplementedError

    def generate_structured(
        self, prompt: str, schema: dict, system_prompt: Optional[str] = None
    ) -> dict:
        """
        Return a response constrained to *schema* (JSON Schema-like dict).

        Not every provider needs this yet — default raises until a caller
        actually needs structured output.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support generate_structured yet")

    def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        """
        Yield response text incrementally.

        Default falls back to a single chunk via generate() — providers that
        support real streaming should override this.
        """
        yield self.generate(prompt, system_prompt=system_prompt)
