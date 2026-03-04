"""Structured logging configuration for Forge agencies."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class StructuredFormatter(logging.Formatter):
    """
    JSON-structured log formatter.

    Every log entry includes: timestamp, level, module, message, and any extra data.
    When agents log, entries also include agent_name and trace_id.
    """

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        for field in ("agent_name", "trace_id", "event_type", "tool_name",
                       "cost_usd", "tokens", "duration_ms", "task_preview"):
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value

        # Add any extra data dict
        data = getattr(record, "data", None)
        if data and isinstance(data, dict):
            entry["data"] = data

        # Add exception info
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(entry, default=str)


class HumanFormatter(logging.Formatter):
    """Human-readable formatter with agent context."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        agent = getattr(record, "agent_name", "")
        trace = getattr(record, "trace_id", "")

        prefix = f"{timestamp} [{record.levelname:7s}]"
        if agent:
            prefix += f" [{agent}]"
        if trace:
            prefix += f" [{trace[:12]}]"

        return f"{prefix} {record.getMessage()}"


def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    log_file: str | None = None,
) -> None:
    """
    Configure logging for a Forge agency.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_format: If True, use JSON structured format. If False, human-readable.
        log_file: Optional file path to also write logs to.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    formatter = StructuredFormatter() if json_format else HumanFormatter()
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (always JSON for machine parsing)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(file_handler)


class AgentLogger:
    """
    Convenience logger that automatically includes agent context.

    Usage:
        log = AgentLogger("MyAgent", trace_id="trace-123")
        log.info("Processing task", data={"task": "hello"})
    """

    def __init__(self, agent_name: str, trace_id: str = "", logger_name: str = "forge.agent"):
        self._logger = logging.getLogger(logger_name)
        self.agent_name = agent_name
        self.trace_id = trace_id

    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        extra = {
            "agent_name": self.agent_name,
            "trace_id": self.trace_id,
        }
        extra.update(kwargs)
        self._logger.log(level, message, extra=extra)

    def info(self, message: str, **kwargs: Any) -> None:
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, message, **kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, message, **kwargs)
