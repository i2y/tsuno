"""
Error logging functionality for tsuno.

Provides Gunicorn/Uvicorn-compatible error logging to file or stderr.
"""

import logging
import sys

# Optional no longer needed (using | None syntax)

# Global error logger
_error_logger: logging.Logger | None = None


def setup_error_logging(
    log_file: str | None = None,
    log_level: str = "INFO",
) -> logging.Logger:
    """
    Set up error logging.

    Args:
        log_file: File path for error log (None = stderr, "-" = stderr)
        log_level: Log level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Logger instance
    """
    global _error_logger

    if _error_logger is None:
        _error_logger = logging.getLogger("tsuno.error")

        # Clear existing handlers
        _error_logger.handlers.clear()

        # Determine output destination
        if log_file and log_file != "-":
            # File output
            handler = logging.FileHandler(log_file)
        else:
            # stderr output (default)
            handler = logging.StreamHandler(sys.stderr)

        # Simple formatter for errors
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        _error_logger.addHandler(handler)

        # Set log level
        level = getattr(logging, log_level.upper(), logging.INFO)
        _error_logger.setLevel(level)
        _error_logger.propagate = False

    return _error_logger


def get_error_logger() -> logging.Logger | None:
    """
    Get the current error logger instance.

    Returns:
        Logger instance or None if not set up
    """
    return _error_logger


def log_error(message: str, *args, **kwargs) -> None:
    """
    Log an error message (convenience function).

    Args:
        message: Error message
        *args: Additional positional arguments
        **kwargs: Additional keyword arguments
    """
    if _error_logger:
        _error_logger.error(message, *args, **kwargs)


def log_warning(message: str, *args, **kwargs) -> None:
    """
    Log a warning message (convenience function).

    Args:
        message: Warning message
        *args: Additional positional arguments
        **kwargs: Additional keyword arguments
    """
    if _error_logger:
        _error_logger.warning(message, *args, **kwargs)


def log_info(message: str, *args, **kwargs) -> None:
    """
    Log an info message (convenience function).

    Args:
        message: Info message
        *args: Additional positional arguments
        **kwargs: Additional keyword arguments
    """
    if _error_logger:
        _error_logger.info(message, *args, **kwargs)
