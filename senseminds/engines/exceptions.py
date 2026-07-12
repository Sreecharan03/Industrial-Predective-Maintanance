"""Engine exception hierarchy.

Shared across all deterministic engines. Data-quality edge cases (sparse,
constant, empty sensors) are handled *gracefully* inside engines and never
raise - these exceptions are reserved for genuinely invalid inputs (contract
violations), so a raised EngineError always means "the caller wired something
wrong", not "the data looks unusual".
"""

from __future__ import annotations


class EngineError(Exception):
    """Base class for all engine errors."""


class EngineInputError(EngineError):
    """An engine was given inputs that violate its contract.

    e.g. a statistics result for a different unit than the series, or a series
    whose sensor has no matching statistics entry.
    """
