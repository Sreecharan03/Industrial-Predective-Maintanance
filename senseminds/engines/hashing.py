"""Shared input-hashing for engine provenance.

A stable content hash of the exact frame an engine consumed, recorded in every
`EngineResult.provenance.input_hash` so a result can be tied to the precise
input that produced it (ADR-004).
"""

from __future__ import annotations

import hashlib

import pandas as pd


def frame_hash(frame: pd.DataFrame) -> str:
    """Return a short stable hash of a DataFrame's contents (order-sensitive)."""
    digest = hashlib.sha256(pd.util.hash_pandas_object(frame, index=False).values.tobytes())
    return digest.hexdigest()[:16]
