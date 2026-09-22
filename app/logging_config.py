"""Structured JSON logging.

Cloud Logging picks up ``severity`` and ``message`` from JSON written to stdout,
so one formatter serves both local development and Cloud Run.
"""

import json
import logging
import sys
from typing import Any, Final

#: Attributes ``logging`` puts on every record. Anything else an emitter passed
#: through ``extra`` is application metadata and is merged into the JSON object.
_RESERVED: Final[frozenset[str]] = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Render a log record as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialise one record.

        Args:
            record: The record to render.

        Returns:
            A JSON string with ``severity``, ``message`` and any extra metadata.
        """
        payload: dict[str, Any] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        payload.update(
            {key: value for key, value in record.__dict__.items() if key not in _RESERVED}
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    """Send structured logs to stdout at the given level.

    Args:
        level: Root log level name, for example ``"INFO"``.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Access logs would duplicate the request log emitted by the middleware.
    logging.getLogger("uvicorn.access").disabled = True
