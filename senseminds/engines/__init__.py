"""Deterministic analytics engines (refactored Phase-1/2 steps).

Each engine is a stateless service with a typed input (`IngestedSeries` or a
prior engine result) and a typed `EngineResult` output. Pandas lives here and
in ingestion, never in the domain or application layers.
"""
