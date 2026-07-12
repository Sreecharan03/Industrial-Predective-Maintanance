"""Engineering Findings layer - the canonical semantic language of SenseMinds.

Deterministic interpretation of validated engine results into immutable
`Finding`s. Not an analytics engine; produces claims, not measurements.
"""

from senseminds.findings.assembler import FindingsAssembler, FindingsError
from senseminds.findings.enums import (
    FindingCategory,
    FindingOrigin,
    FindingScope,
    FindingType,
)
from senseminds.findings.identity import finding_id, identity_key
from senseminds.findings.models import Finding, ObservedWindow

__all__ = [
    "Finding",
    "FindingCategory",
    "FindingOrigin",
    "FindingScope",
    "FindingType",
    "FindingsAssembler",
    "FindingsError",
    "ObservedWindow",
    "finding_id",
    "identity_key",
]
