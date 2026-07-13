"""Which findings are worth recording again? (application policy)

Findings are append-only, and `finding_id = hash(identity, input_hash)` — so a
re-analysis of *any* new reading produces a brand-new finding_id for a condition
that has not actually changed. Persisting all of them writes thousands of rows a
day that say the same thing, and makes the graph's condition nodes accumulate an
unbounded list of finding ids.

So the application decides what counts as a **material change**: a genuinely new
condition, a change in severity or wording, a meaningful move in confidence, or a
meaningful move in the evidence values. Sensor noise is not a new observation.

This is a policy, not a repository concern — the repository stays a dumb mapper.
"""

from __future__ import annotations

import re

from senseminds.findings import Finding

_CONFIDENCE_TOL = 0.05   # a 5-point swing in confidence is worth recording
_VALUE_REL_TOL = 0.02    # evidence values that move >2% are worth recording

# Engines write the numbers into the prose ("health is reduced (86.8)"), so comparing
# the text directly would call every tiny wobble a new observation and defeat the
# tolerances below. Compare the *wording*, and let the evidence values decide whether
# the numbers moved enough to matter.
_NUMBER = re.compile(r"[-+]?\d[\d,]*\.?\d*")


def _wording(text: str) -> str:
    return _NUMBER.sub("#", text)


def _same_value(a: object, b: object) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a == b:
            return True
        scale = max(abs(float(a)), abs(float(b)), 1e-9)
        return abs(float(a) - float(b)) / scale <= _VALUE_REL_TOL
    return a == b


def is_material_change(previous: Finding | None, current: Finding) -> bool:
    """True if `current` says something new relative to the last observation."""
    if previous is None:
        return True  # a condition we have never seen

    if (
        previous.finding_type,
        previous.category,
        previous.origin,
        previous.severity,
        previous.target_key,
        previous.subsystem_key,
        _wording(previous.summary),
        _wording(previous.detail),
        previous.triggered_by,
    ) != (
        current.finding_type,
        current.category,
        current.origin,
        current.severity,
        current.target_key,
        current.subsystem_key,
        _wording(current.summary),
        _wording(current.detail),
        current.triggered_by,
    ):
        return True

    if abs(previous.confidence.value - current.confidence.value) > _CONFIDENCE_TOL:
        return True

    if len(previous.evidence) != len(current.evidence):
        return True
    for before, now in zip(previous.evidence, current.evidence, strict=True):
        if (before.artifact_id, before.description) != (now.artifact_id, now.description):
            return True
        if not _same_value(before.observed_value, now.observed_value):
            return True

    return False
