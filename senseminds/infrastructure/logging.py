"""Structured JSON logging.

Every platform process configures logging exactly once, at startup, via
`configure_logging()`. Log records are emitted as single-line JSON so they are
machine-parseable by downstream observability tooling without a bespoke
parser. `bind()` returns a `LoggerAdapter` that stamps stable context (asset,
run id, ...) onto every record it emits - the mechanism by which a finding can
later be traced back through the logs that produced it.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_CONFIGURED = False

# Attributes present on every stdlib LogRecord; anything else a caller attached
# via `extra=` is treated as structured context and included in the JSON output.
_RESERVED = set(
    logging.makeLogRecord({}).__dict__.keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as one line of JSON, preserving `extra` context."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Idempotently install the JSON formatter on the root logger."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    _CONFIGURED = True


def get_logger(name: str, **context: object) -> logging.LoggerAdapter:
    """Return a logger that stamps `context` onto every record it emits."""
    return logging.LoggerAdapter(logging.getLogger(name), dict(context))
