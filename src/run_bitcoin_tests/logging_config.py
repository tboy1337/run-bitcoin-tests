"""
Logging configuration for the Bitcoin Core tests runner.

This module provides centralized logging configuration with appropriate
log levels, formatting, and output destinations for different environments.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional


def setup_logging(
    level: str = "INFO", log_file: Optional[str] = None, verbose: bool = False, quiet: bool = False
) -> logging.Logger:
    """
    Set up logging configuration for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path to write logs to
        verbose: Enable verbose output (DEBUG level)
        quiet: Suppress all output except errors

    Returns:
        Configured logger instance
    """
    # Determine log level
    if verbose:
        log_level = logging.DEBUG
    elif quiet:
        log_level = logging.ERROR
    else:
        log_level = getattr(logging, level.upper(), logging.INFO)

    # Create logger
    logger = logging.getLogger("bitcoin_tests")
    logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create formatter
    if verbose:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
        )
    else:
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    # Filter out colorama escape sequences from log output
    class ColorFilter(logging.Filter):
        def filter(self, record):
            # Remove ANSI escape sequences from log messages
            import re

            if hasattr(record, "msg") and isinstance(record.msg, str):
                record.msg = re.sub(r"\x1b\[[0-9;]*m", "", record.msg)
            return True

    console_handler.addFilter(ColorFilter())
    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        try:
            # Ensure log directory exists
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            # Use rotating file handler to prevent log files from growing too large
            file_handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=10 * 1024 * 1024, backupCount=5  # 10MB
            )
            file_handler.setLevel(logging.DEBUG)  # Always log debug to file
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            logger.info(f"Logging to file: {log_file}")
        except Exception as e:
            logger.warning(f"Could not set up file logging: {e}")

    # Log the startup
    logger.info(
        f"Bitcoin Core Tests Runner started with log level: {logging.getLevelName(log_level)}"
    )

    return logger


def get_logger(name: str = "bitcoin_tests") -> logging.Logger:
    """
    Get a logger instance for the specified name.

    Args:
        name: Logger name (will be prefixed with 'bitcoin_tests.')

    Returns:
        Logger instance
    """
    return logging.getLogger(f"bitcoin_tests.{name}")


# Global logger instance
logger = get_logger()
