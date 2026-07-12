"""Shared engine base.

Every deterministic engine subclasses `BaseEngine`, which centralises the two
things every engine repeated by hand: its identity (name/version) and building
`Provenance` for its result (ADR-011 finding 2.3). It deliberately does NOT fix
a `compute` signature - engines consume different upstream contracts - so it
adds consistency without leaking a false uniformity.
"""

from __future__ import annotations

import logging
from abc import ABC
from typing import ClassVar

import pandas as pd

from senseminds.domain.value_objects import Provenance
from senseminds.engines.hashing import frame_hash
from senseminds.infrastructure.logging import get_logger


class BaseEngine(ABC):
    """Base for deterministic engines: identity + provenance construction."""

    name: ClassVar[str]
    version: ClassVar[str]

    @property
    def log(self) -> logging.LoggerAdapter:
        return get_logger(f"senseminds.engines.{self.name}")

    def provenance(self, source_unit: str, *, input_hash: str) -> Provenance:
        """Build provenance for a result of this engine."""
        return Provenance(
            engine=self.name,
            engine_version=self.version,
            source_unit=source_unit,
            input_hash=input_hash,
        )

    def provenance_from_frame(self, source_unit: str, frame: pd.DataFrame) -> Provenance:
        """Provenance whose input hash is the content hash of ``frame``."""
        return self.provenance(source_unit, input_hash=frame_hash(frame))
