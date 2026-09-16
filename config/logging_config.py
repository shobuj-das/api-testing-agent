"""Structured logging configuration with sensitive data masking and file logging under logs/."""

from __future__ import annotations

import logging
from pathlib import Path

from clients.api_client import mask_sensitive_text

DEFAULT_LOG_DIR = Path("logs")
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "agent.log"


class MaskingFormatter(logging.Formatter):
    """Logging formatter that automatically masks credentials, tokens, and secrets."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return mask_sensitive_text(original)


def setup_logging(
    log_file: str | Path = DEFAULT_LOG_FILE,
    *,
    verbose: bool = False,
    log_to_console: bool = True,
) -> logging.Logger:
    """Configure structured logging for the API testing agent."""
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("api_testing_agent")
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Avoid adding duplicate handlers if already initialized
    if root_logger.handlers:
        return root_logger

    formatter = MaskingFormatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File Handler
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Console Handler
    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    return root_logger
