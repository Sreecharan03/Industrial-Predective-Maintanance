"""Deterministic finding identity (ADR-013 §4, refined).

`identity_key` = hash(asset_key, finding_type, scope, target_key) - the stable,
**globally unique** identity of a *condition on an entity*. The asset is
included so the same condition on the same-named target of different equipment
(e.g. `oil_pressure` on COM-102 vs COM-110) never collides. It deliberately
excludes the observed window: the window grows as data accumulates across runs,
and including it would break supersession (identity must be stable across
executions). The window rides on the Finding as metadata, not identity.

`finding_id` = hash(identity_key, input_hash) - a specific *observation* of that
condition on specific data. Same condition + same data ⇒ same finding_id
(idempotent); new data ⇒ new finding_id (supersedes the prior one).
"""

from __future__ import annotations

import hashlib

from senseminds.findings.enums import FindingScope, FindingType

_LEN = 16


def identity_key(
    asset_key: str, finding_type: FindingType, scope: FindingScope, target_key: str
) -> str:
    raw = f"{asset_key}|{finding_type.value}|{scope.value}|{target_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:_LEN]


def finding_id(identity: str, input_hash: str) -> str:
    raw = f"{identity}|{input_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:_LEN]
