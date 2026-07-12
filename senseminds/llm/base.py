"""LanguageModel interface (ADR-018).

A pluggable provider seam: the deterministic stub backs all grounding/citation
tests offline, and a real provider (Groq, ...) implements the same contract with
no change to the grounding framework. The model only ever receives assembled
text and returns text - grounding and citation enforcement happen around it, not
inside it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar


class LanguageModel(ABC):
    """Turns an assembled (system, user) prompt into a raw completion string."""

    name: ClassVar[str]

    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Return the model's raw completion (expected to be the JSON contract)."""
