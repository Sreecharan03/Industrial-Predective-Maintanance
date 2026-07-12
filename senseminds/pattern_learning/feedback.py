"""Human-feedback interface (ADR-016 R2).

The contract for future engineer validation of LEARNED findings. NOT consumed in
Phase B - it influences no model or output - but it is the store whose
annotations become Phase C's supervised labels (the label-bootstrap loop).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum

from pydantic import Field

from senseminds.domain.base import FrozenModel


class FeedbackVerdict(StrEnum):
    CONFIRMED_NOVELTY = "confirmed_novelty"
    EXPECTED_BEHAVIOUR = "expected_behaviour"
    FALSE_POSITIVE = "false_positive"


class HumanFeedback(FrozenModel):
    """An engineer's verdict on a LEARNED finding, keyed by its identity."""

    finding_identity_key: str = Field(min_length=1)
    verdict: FeedbackVerdict
    author: str = Field(min_length=1)
    note: str = ""
    created_at: datetime


class FeedbackRepository(ABC):
    """Store and retrieve engineer feedback (future Phase-C label source)."""

    @abstractmethod
    def record(self, feedback: HumanFeedback) -> None: ...

    @abstractmethod
    def for_finding(self, identity_key: str) -> list[HumanFeedback]: ...

    @abstractmethod
    def all(self) -> list[HumanFeedback]: ...


class InMemoryFeedbackRepository(FeedbackRepository):
    def __init__(self) -> None:
        self._items: list[HumanFeedback] = []

    def record(self, feedback: HumanFeedback) -> None:
        self._items.append(feedback)

    def for_finding(self, identity_key: str) -> list[HumanFeedback]:
        return [f for f in self._items if f.finding_identity_key == identity_key]

    def all(self) -> list[HumanFeedback]:
        return list(self._items)
