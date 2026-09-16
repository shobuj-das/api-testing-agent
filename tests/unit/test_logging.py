"""Unit tests for structured logging and sensitive data masking."""

import logging
from pathlib import Path

from config.logging_config import MaskingFormatter, setup_logging


def test_masking_formatter_redacts_tokens() -> None:
    formatter = MaskingFormatter(fmt="%(message)s")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Request header: Bearer super_secret_jwt_token_123",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    assert "super_secret_jwt_token_123" not in formatted
    assert "Bearer ***MASKED***" in formatted


def test_setup_logging_writes_to_file(tmp_path: Path) -> None:
    log_file = tmp_path / "test_agent.log"
    logger = setup_logging(log_file=log_file, verbose=True, log_to_console=False)
    logger.info("Test message with token abc123def456")

    # Flush handlers
    for handler in logger.handlers:
        handler.flush()

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "Test message" in content
