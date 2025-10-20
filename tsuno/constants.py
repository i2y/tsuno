"""
Constants and enums for HTTP server configuration.
"""

from enum import Enum


class HttpVersion(Enum):
    """HTTP version configuration."""

    HTTP_1_1 = "1.1"
    HTTP_2 = "2"
    AUTO = "auto"  # Automatic negotiation
