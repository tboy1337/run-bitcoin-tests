"""Tests for logging configuration module."""

import logging
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from run_bitcoin_tests.logging_config import get_logger, setup_logging


class TestSetupLogging:
    """Test logging setup functionality."""

    def test_setup_logging_default(self):
        """Test setup_logging with default parameters."""
        logger = setup_logging()

        assert logger.name == "bitcoin_tests"
        assert logger.level == logging.INFO
        assert len(logger.handlers) >= 1  # At least console handler

    def test_setup_logging_verbose(self):
        """Test setup_logging with verbose=True."""
        logger = setup_logging(verbose=True)

        assert logger.level == logging.DEBUG
        # Check that verbose formatter is used
        console_handler = next(
            (h for h in logger.handlers if isinstance(h, logging.StreamHandler)), None
        )
        assert console_handler is not None
        formatter = console_handler.formatter
        assert "funcName" in formatter._fmt

    def test_setup_logging_quiet(self):
        """Test setup_logging with quiet=True."""
        logger = setup_logging(quiet=True)

        assert logger.level == logging.ERROR

    def test_setup_logging_custom_level(self):
        """Test setup_logging with custom log level."""
        logger = setup_logging(level="WARNING")

        assert logger.level == logging.WARNING

    def test_setup_logging_invalid_level(self):
        """Test setup_logging with invalid log level defaults to INFO."""
        logger = setup_logging(level="INVALID")

        assert logger.level == logging.INFO

    @patch("pathlib.Path.mkdir")
    def test_setup_logging_with_file(self, mock_mkdir):
        """Test setup_logging with log file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "test.log"

            logger = setup_logging(log_file=str(temp_path))

            # Should have both console and file handlers
            handlers = logger.handlers
            assert len(handlers) >= 2

            # Check for rotating file handler
            file_handler = next(
                (h for h in handlers if isinstance(h, logging.handlers.RotatingFileHandler)), None
            )
            assert file_handler is not None
            assert file_handler.maxBytes == 10 * 1024 * 1024  # 10MB
            assert file_handler.backupCount == 5

            # Close handlers to allow cleanup
            for handler in logger.handlers:
                handler.close()
            logger.handlers.clear()

    @patch("pathlib.Path.mkdir", side_effect=Exception("Permission denied"))
    def test_setup_logging_file_creation_error(self, mock_mkdir):
        """Test setup_logging handles file creation errors gracefully."""
        # This is tricky to test directly, so we'll test that the function
        # doesn't crash and continues with console logging
        logger = setup_logging(log_file="/invalid/path/log.txt")

        # Should still have at least console handler
        assert len(logger.handlers) >= 1

    def test_setup_logging_removes_existing_handlers(self):
        """Test that setup_logging removes existing handlers."""
        logger = logging.getLogger("bitcoin_tests")

        # Add a dummy handler
        dummy_handler = logging.NullHandler()
        logger.addHandler(dummy_handler)

        # Setup logging again
        setup_logging()

        # Dummy handler should be removed
        assert dummy_handler not in logger.handlers

    def test_setup_logging_color_filter(self):
        """Test that color filter is added to console handler."""
        logger = setup_logging()

        console_handler = next(
            (h for h in logger.handlers if isinstance(h, logging.StreamHandler)), None
        )
        assert console_handler is not None

        # Check for ColorFilter
        color_filter = next((f for f in console_handler.filters if hasattr(f, "filter")), None)
        assert color_filter is not None

    def test_color_filter_removes_ansi_codes(self):
        """Test that ColorFilter removes ANSI escape codes."""
        from run_bitcoin_tests.logging_config import setup_logging

        logger = setup_logging()
        console_handler = next(
            (h for h in logger.handlers if isinstance(h, logging.StreamHandler)), None
        )
        color_filter = next((f for f in console_handler.filters if hasattr(f, "filter")), None)

        # Create a mock log record with ANSI codes
        record = Mock()
        record.msg = "\x1b[31mRed text\x1b[0m normal text"

        # Apply filter
        result = color_filter.filter(record)

        assert result is True
        assert record.msg == "Red text normal text"


class TestGetLogger:
    """Test get_logger function."""

    def test_get_logger_default(self):
        """Test get_logger with default parameters."""
        logger = get_logger()

        assert logger.name == "bitcoin_tests.bitcoin_tests"

    def test_get_logger_custom_name(self):
        """Test get_logger with custom name."""
        logger = get_logger("custom")

        assert logger.name == "bitcoin_tests.custom"

    def test_get_logger_returns_same_instance(self):
        """Test get_logger returns same instance for same name."""
        logger1 = get_logger("test")
        logger2 = get_logger("test")

        assert logger1 is logger2


class TestGlobalLogger:
    """Test global logger instance."""

    def test_global_logger_exists(self):
        """Test that global logger is properly initialized."""
        from run_bitcoin_tests.logging_config import logger

        assert logger.name == "bitcoin_tests.bitcoin_tests"
        assert isinstance(logger, logging.Logger)
