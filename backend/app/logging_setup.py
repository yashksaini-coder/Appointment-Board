"""Structured logging for the appointment board.

Call sites look like:

    log.info("appointment.created", extra=fields(appointment_id=8, date="2026-09-09"))

The message is a stable dotted event name you can grep or facet on; everything
variable rides in `fields`. Nesting the structured data under one key rather
than splatting it onto the LogRecord matters for two reasons: `extra` keys
collide with reserved record attributes (`extra={"module": ...}` raises KeyError
inside logging itself), and a stray key would otherwise overwrite the JSON
envelope. One key, no denylist to maintain.
"""

import json
import logging
import logging.config
import os
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

# Set by the access-log middleware and read by the formatters. A ContextVar
# survives into the threadpool FastAPI uses for `def` endpoints, so sync routes
# get the right id without threading it through every signature.
request_id: ContextVar[str] = ContextVar("request_id", default="-")

HEALTH_PATH = "/api/health"


def fields(**kwargs) -> dict:
    """Wrap structured fields for `extra=`."""
    return {"fields": kwargs}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            "logger": record.name,
            "request_id": request_id.get(),
            "pid": record.process,
        }
        extra = getattr(record, "fields", None)
        if extra:
            payload["fields"] = extra
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        try:
            return json.dumps(payload, default=str)
        except (TypeError, ValueError):
            # A dropped record is worse than a lossy one: json.dumps failing
            # inside format() makes logging swallow the line entirely.
            payload["fields"] = {"unserialisable": repr(extra)}
            return json.dumps(payload, default=str)


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        extra = getattr(record, "fields", None) or {}
        stamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        line = f"{stamp} {record.levelname:<7} [{request_id.get()}] {record.getMessage()}"
        if extra:
            line += "  " + " ".join(f"{k}={v}" for k, v in extra.items())
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging() -> None:
    """Install one root handler. Call at import time, before uvicorn starts.

    Uvicorn configures logging in Config.__init__, which runs *before* it
    imports the app, and its own config has no root entry -- so configuring at
    import time wins and also captures uvicorn's startup lines in our format.

    The exception is `--reload`: the reloader is a separate parent process that
    never imports the app, so its first few lines keep uvicorn's own format.
    """
    fmt = os.getenv("LOG_FORMAT", "console").strip().lower()
    if fmt not in ("console", "json"):
        raise ValueError(f"LOG_FORMAT must be 'console' or 'json', got {fmt!r}")

    # Validated the same way as LOG_FORMAT: an unknown level otherwise fails
    # deep inside dictConfig with a message that names neither the variable
    # nor the value.
    level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    if level not in logging.getLevelNamesMapping():
        raise ValueError(
            f"LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL; got {level!r}"
        )

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "console": {"()": ConsoleFormatter},
                "json": {"()": JsonFormatter},
            },
            "handlers": {
                "stderr": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stderr,
                    "formatter": fmt,
                }
            },
            "root": {"handlers": ["stderr"], "level": level},
            "loggers": {
                # Let uvicorn's own records flow through our handler instead of
                # its default one, so the stream has a single format...
                "uvicorn": {"handlers": [], "propagate": True},
                "uvicorn.error": {"handlers": [], "propagate": True},
                # ...except its access log, which our `request` event replaces.
                "uvicorn.access": {"handlers": [], "propagate": False},
            },
        }
    )
