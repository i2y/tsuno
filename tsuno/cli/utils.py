"""
Utility functions for the z CLI.

This module provides helpers for:
- Application importing and validation
- Module path manipulation
- Error handling
"""

import importlib
import sys
from pathlib import Path
from typing import Any


class ApplicationLoadError(Exception):
    """Raised when an application cannot be loaded."""

    pass


def import_app(module_str: str, factory: bool = False, app_dir: str | None = None) -> Any:
    """
    Import application from module string.

    Args:
        module_str: Module string in format "module:attribute" or just "module"
        factory: If True, treat the imported object as a factory function
        app_dir: Optional directory to add to PYTHONPATH

    Returns:
        The imported application object

    Raises:
        ApplicationLoadError: If the application cannot be loaded

    Examples:
        >>> app = import_app("myapp:application")
        >>> app = import_app("myapp:create_app", factory=True)
        >>> app = import_app("main:app", app_dir="./src")
    """
    # Add app_dir to Python path if specified
    if app_dir:
        app_path = Path(app_dir).resolve()
        if not app_path.exists():
            raise ApplicationLoadError(f"Application directory not found: {app_dir}")
        if not app_path.is_dir():
            raise ApplicationLoadError(f"Application directory is not a directory: {app_dir}")
        sys.path.insert(0, str(app_path))

    # Parse module string
    if ":" in module_str:
        module_name, _, attr_name = module_str.partition(":")
    else:
        # Default to looking for common attribute names
        module_name = module_str
        attr_name = None

    # Import the module
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise ApplicationLoadError(f"Could not import module '{module_name}': {e}") from e

    # Get the application object
    if attr_name:
        try:
            app = getattr(module, attr_name)
        except AttributeError:
            raise ApplicationLoadError(f"Module '{module_name}' has no attribute '{attr_name}'")
    else:
        # Try common names
        for name in ["application", "app", "create_app"]:
            if hasattr(module, name):
                app = getattr(module, name)
                if name == "create_app":
                    factory = True  # Auto-detect factory pattern
                break
        else:
            raise ApplicationLoadError(
                f"Module '{module_name}' has no 'application', 'app', or 'create_app' attribute. "
                "Please specify the attribute explicitly (e.g., 'module:app')"
            )

    # Call factory if needed
    if factory:
        if not callable(app):
            raise ApplicationLoadError(
                f"Application factory '{attr_name or 'app'}' is not callable"
            )
        try:
            app = app()
        except Exception as e:
            raise ApplicationLoadError(f"Error calling application factory: {e}") from e

    return app


def parse_mount_spec(mount_spec: str) -> tuple[str, str]:
    """
    Parse a mount specification string.

    Args:
        mount_spec: Mount specification in format "path:module_str"

    Returns:
        Tuple of (path, module_str)

    Raises:
        ValueError: If the mount specification is invalid

    Examples:
        >>> parse_mount_spec("/api:api.app:application")
        ('/api', 'api.app:application')
    """
    if ":" not in mount_spec:
        raise ValueError(
            f"Invalid mount specification: '{mount_spec}'. "
            "Expected format: 'path:module' or 'path:module:attribute'"
        )

    # Split on first colon
    path, _, rest = mount_spec.partition(":")

    if not path.startswith("/"):
        raise ValueError(
            f"Mount path must start with '/': '{path}'. Example: '/api:api.app:application'"
        )

    return path, rest


def validate_bind_address(bind: str) -> tuple[str, int]:
    """
    Validate and parse bind address.

    Args:
        bind: Bind address in format "host:port"

    Returns:
        Tuple of (host, port)

    Raises:
        ValueError: If the bind address is invalid

    Examples:
        >>> validate_bind_address("0.0.0.0:8000")
        ('0.0.0.0', 8000)
        >>> validate_bind_address("localhost:3000")
        ('localhost', 3000)
    """
    if ":" not in bind:
        raise ValueError(f"Invalid bind address: '{bind}'. Expected format: 'host:port'")

    host, _, port_str = bind.partition(":")

    try:
        port = int(port_str)
    except ValueError:
        raise ValueError(f"Invalid port number: '{port_str}'. Must be an integer.")

    if port < 1 or port > 65535:
        raise ValueError(f"Port number must be between 1 and 65535, got: {port}")

    return host, port
