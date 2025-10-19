"""
Access logging functionality for z.

Provides Uvicorn-compatible access logging with customizable formats.
"""

import logging
import sys

# Optional no longer needed (using | None syntax)

logger = logging.getLogger("z.access")


class AccessLogFormatter(logging.Formatter):
    """
    Custom formatter for access logs that supports color output.

    Compatible with Uvicorn's access log format:
    '{client_addr} - "{method} {path} HTTP/{http_version}" {status_code}'
    """

    # Status code colors (ANSI escape codes)
    STATUS_COLORS = {
        1: "\033[96m",  # Cyan (1xx - Informational)
        2: "\033[92m",  # Green (2xx - Success)
        3: "\033[93m",  # Yellow (3xx - Redirection)
        4: "\033[91m",  # Red (4xx - Client Error)
        5: "\033[95m",  # Magenta (5xx - Server Error)
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    def __init__(self, fmt: str | None = None, use_colors: bool = True):
        """
        Initialize the formatter.

        Args:
            fmt: Log format string (optional)
            use_colors: Enable colored output
        """
        super().__init__(fmt)
        self.use_colors = use_colors and self._supports_color()

    @staticmethod
    def _supports_color() -> bool:
        """
        Check if the terminal supports color output.

        Returns:
            True if color is supported, False otherwise
        """
        # Check if stdout is a TTY
        if not hasattr(sys.stdout, "isatty"):
            return False
        if not sys.stdout.isatty():
            return False

        # Check for NO_COLOR environment variable
        import os

        if os.getenv("NO_COLOR"):
            return False

        # Check platform
        if sys.platform == "win32":
            # Windows 10+ supports ANSI colors
            return True

        # Unix-like systems support ANSI colors
        return True

    def _get_status_color(self, status_code: int) -> str:
        """
        Get the ANSI color code for a given status code.

        Args:
            status_code: HTTP status code

        Returns:
            ANSI color code or empty string if colors disabled
        """
        if not self.use_colors:
            return ""

        status_class = status_code // 100
        return self.STATUS_COLORS.get(status_class, "")

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record.

        Args:
            record: Log record to format

        Returns:
            Formatted log string
        """
        # Extract attributes from record
        client_addr = getattr(record, "client_addr", "-")
        method = getattr(record, "method", "-")
        path = getattr(record, "path", "-")
        http_version = getattr(record, "http_version", "1.1")
        status_code = getattr(record, "status_code", 0)
        duration = getattr(record, "duration", 0.0)

        # Format the basic log message
        if self.use_colors:
            # Colored format (similar to Uvicorn)
            status_color = self._get_status_color(status_code)
            msg = (
                f"{self.DIM}{client_addr}{self.RESET} - "
                f'"{self.BOLD}{method}{self.RESET} {path} '
                f'HTTP/{http_version}" '
                f"{status_color}{status_code}{self.RESET}"
            )

            # Add duration if available
            if duration > 0:
                msg += f" {self.DIM}({duration:.2f}s){self.RESET}"
        else:
            # Plain format
            msg = (
                f"{client_addr} - "
                f'"{method} {path} HTTP/{http_version}" '
                f"{status_code}"
            )

            # Add duration if available
            if duration > 0:
                msg += f" ({duration:.2f}s)"

        return msg


class AccessLogger:
    """
    Access logger that captures HTTP request/response information.
    """

    def __init__(
        self,
        logger_name: str = "z.access",
        format_string: str | None = None,
        use_colors: bool = True,
    ):
        """
        Initialize the access logger.

        Args:
            logger_name: Name of the logger
            format_string: Custom format string (optional)
            use_colors: Enable colored output
        """
        self.logger = logging.getLogger(logger_name)
        self.use_colors = use_colors

        # Set up formatter if not already configured
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = AccessLogFormatter(format_string, use_colors=use_colors)
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
            self.logger.propagate = False

    def log(
        self,
        client_addr: str,
        method: str,
        path: str,
        http_version: str,
        status_code: int,
        duration: float | None = None,
    ) -> None:
        """
        Log an HTTP request/response.

        Args:
            client_addr: Client IP address
            method: HTTP method (GET, POST, etc.)
            path: Request path
            http_version: HTTP version (1.0, 1.1, 2.0)
            status_code: HTTP status code
            duration: Request duration in seconds (optional)
        """
        # Create a log record with extra attributes
        extra = {
            "client_addr": client_addr,
            "method": method,
            "path": path,
            "http_version": http_version,
            "status_code": status_code,
            "duration": duration or 0.0,
        }

        # Log at INFO level
        self.logger.info("", extra=extra)


# Global access logger instance
_access_logger: AccessLogger | None = None


def setup_access_logging(
    enabled: bool = True,
    use_colors: bool | None = None,
    format_string: str | None = None,
    log_file: str | None = None,
) -> AccessLogger | None:
    """
    Set up access logging.

    Args:
        enabled: Enable access logging
        use_colors: Enable colored output (None = auto-detect TTY)
        format_string: Custom format string (optional)
        log_file: File path for access log (None = stdout, "-" = stdout)

    Returns:
        AccessLogger instance if enabled, None otherwise
    """
    global _access_logger

    if not enabled:
        _access_logger = None
        return None

    # Auto-detect TTY if use_colors is None
    if use_colors is None:
        import sys

        use_colors = sys.stdout.isatty()

    if _access_logger is None:
        logger = logging.getLogger("z.access")

        # Clear existing handlers
        logger.handlers.clear()

        # Determine output destination
        if log_file and log_file != "-":
            # File output
            handler = logging.FileHandler(log_file)
            # Disable colors for file output
            formatter = AccessLogFormatter(format_string, use_colors=False)
        else:
            # stdout output
            import sys

            handler = logging.StreamHandler(sys.stdout)
            formatter = AccessLogFormatter(format_string, use_colors=use_colors)  # type: ignore

        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False

        _access_logger = AccessLogger(
            format_string=format_string,
            use_colors=use_colors if not log_file or log_file == "-" else False,  # type: ignore
        )

    return _access_logger


def get_access_logger() -> AccessLogger | None:
    """
    Get the current access logger instance.

    Returns:
        AccessLogger instance or None if not set up
    """
    return _access_logger


def log_request(
    client_addr: str,
    method: str,
    path: str,
    http_version: str,
    status_code: int,
    duration: float | None = None,
) -> None:
    """
    Log an HTTP request (convenience function).

    Args:
        client_addr: Client IP address
        method: HTTP method
        path: Request path
        http_version: HTTP version
        status_code: HTTP status code
        duration: Request duration in seconds (optional)
    """
    if _access_logger:
        _access_logger.log(
            client_addr=client_addr,
            method=method,
            path=path,
            http_version=http_version,
            status_code=status_code,
            duration=duration,
        )
