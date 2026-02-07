"""Structured logging helpers."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_obj["exception"] = self.formatException(record.exc_info)
        # Merge any extra fields attached via `extra={...}`
        for key in ("campaign_id", "provider_id", "call_sid", "detail"):
            val = getattr(record, key, None)
            if val is not None:
                log_obj[key] = val
        return json.dumps(log_obj, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with JSON output to stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers on repeated calls
    if not root.handlers:
        root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (call setup_logging first)."""
    return logging.getLogger(name)
