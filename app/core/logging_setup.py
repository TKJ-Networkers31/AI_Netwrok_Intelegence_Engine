"""Structured application logging setup.

Log records carry a component/event style similar to structured logging,
via the `extra={...}` mechanism on the standard `logging` module. This
keeps Phase 0 dependency-free (no external logging library) while still
producing consistent, parseable output.
"""

from __future__ import annotations

import logging

_DEFAULT_FORMAT = (
    "%(asctime)s level=%(levelname)s component=%(component)s "
    "event=%(event)s request_id=%(request_id)s message=%(message)s"
)


class _DefaultFieldsFilter(logging.Filter):
    """Ensures component/event/request_id are always present so the format
    string above never raises a KeyError for log calls that don't pass them.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "component"):
            record.component = "-"
        if not hasattr(record, "event"):
            record.event = "-"
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


def configure_logging(log_level: str = "INFO") -> None:
    """Configure root logging for the `anie` logger hierarchy.

    Safe to call multiple times (e.g. in tests) — it clears existing
    handlers on the `anie` logger before reconfiguring.
    """
    logger = logging.getLogger("anie")
    logger.setLevel(log_level)
    logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    handler.addFilter(_DefaultFieldsFilter())
    logger.addHandler(handler)
    logger.propagate = False
