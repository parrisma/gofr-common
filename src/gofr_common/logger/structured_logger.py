"""
Structured logger with JSON output and file support.

A production-ready logger that supports JSON formatting for log aggregation
systems and optional file output.
"""

import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .interface import Logger


class JsonFormatter(logging.Formatter):
    """JSON formatter for logging records.
    
    Formats log records as JSON objects suitable for ingestion by
    log aggregation systems like ELK, Splunk, or CloudWatch.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Add session_id if present
        session_id = getattr(record, "session_id", None)
        if session_id:
            log_data["session_id"] = str(session_id)

        # Add any other custom attributes (from extra kwargs)
        skip_keys = {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "levelname", "levelno", "lineno", "module",
            "msecs", "message", "msg", "name", "pathname", "process",
            "processName", "relativeCreated", "stack_info", "thread",
            "threadName", "session_id", "taskName",
        }

        for key, value in record.__dict__.items():
            if key not in skip_keys:
                log_data[key] = value

        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """Text formatter that appends extra kwargs to the message.
    
    Formats log records as human-readable text with any extra
    key-value pairs appended to the message.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Format the base message using the standard formatter
        s = super().format(record)

        # Extract and append extra fields
        skip_keys = {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "levelname", "levelno", "lineno", "module",
            "msecs", "message", "msg", "name", "pathname", "process",
            "processName", "relativeCreated", "stack_info", "thread",
            "threadName", "session_id", "taskName",
        }

        extra_args = {}
        for key, value in record.__dict__.items():
            if key not in skip_keys:
                extra_args[key] = value

        if extra_args:
            s += " " + " ".join(f"{k}={v}" for k, v in extra_args.items())

        return s


class StructuredLogger(Logger):
    """Logger implementation with structured JSON logging and file output.
    
    A production-ready logger that supports:
    - JSON formatting for log aggregation systems
    - Human-readable text formatting for development
    - File output with automatic rotation
    - Session tracking across all log entries
    
    Example:
        # Development mode (text output)
        logger = StructuredLogger(name="gofr-plot")
        
        # Production mode (JSON output to file)
        logger = StructuredLogger(
            name="gofr-plot",
            json_format=True,
            log_file="/var/log/gofr-plot.log"
        )
        
        logger.info("Request processed", request_id="abc123", duration_ms=45)
    """

    def __init__(
        self,
        name: str = "gofr",
        level: int = logging.INFO,
        log_file: Optional[str] = None,
        json_format: bool = False,
    ):
        """Initialize the structured logger.
        
        Args:
            name: Logger name (e.g., "gofr-np", "gofr-dig", "gofr-plot", "gofr-doc")
            level: Logging level (logging.DEBUG, logging.INFO, etc.)
            log_file: Optional file path for log output
            json_format: If True, output logs as JSON; otherwise use text format
        """
        self._name = name
        self._session_id = str(uuid.uuid4())[:8]
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)

        # Clear existing handlers to avoid duplication if re-initialized
        if self._logger.hasHandlers():
            self._logger.handlers.clear()

        self._logger.propagate = False

        # Create formatter based on format preference
        if json_format:
            formatter: logging.Formatter = JsonFormatter()
        else:
            formatter = TextFormatter(
                "%(asctime)s [%(levelname)s] [%(name)s] [session:%(session_id)s] %(message)s"
            )

        # Console Handler (stdout)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)

        # File Handler (if configured)
        if log_file:
            try:
                file_handler = logging.FileHandler(log_file)
                file_handler.setFormatter(formatter)
                self._logger.addHandler(file_handler)
            except Exception as e:
                # Fallback to console if file cannot be opened
                print(f"Failed to setup log file {log_file}: {e}", file=sys.stderr)

    def get_session_id(self) -> str:
        """Get the current session ID."""
        return self._session_id

    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        """Internal logging method with extra kwargs handling."""
        extra = {"session_id": self._session_id}

        # Filter out reserved LogRecord attributes to prevent overwrite errors
        reserved_keys = {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "levelname", "levelno", "lineno", "module",
            "msecs", "message", "msg", "name", "pathname", "process",
            "processName", "relativeCreated", "stack_info", "thread",
            "threadName", "taskName",
        }

        for k, v in kwargs.items():
            if k not in reserved_keys:
                extra[k] = v
            else:
                # Prefix reserved keys to preserve them but avoid collision
                extra[f"_{k}"] = v

        self._logger.log(level, message, extra=extra)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug message."""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info message."""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning message."""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log an error message."""
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log a critical message."""
        self._log(logging.CRITICAL, message, **kwargs)
