"""
Main entry point for z CLI.
"""

import argparse
import sys
from typing import Any

from z import __version__

from .config import (ConfigError, get_env_config, load_config_file,
                     merge_configs, normalize_config, validate_config)
from .runner import run_application


def create_parser() -> argparse.ArgumentParser:
    """
    Create and configure the argument parser.

    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        prog="z",
        description="Z - High-performance WSGI/ASGI server with Rust transport",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run a Flask application
  z myapp:app --bind 0.0.0.0:8000 --workers 4

  # Run a FastAPI application with auto-reload
  z main:app --reload

  # Use a factory function
  z myapp:create_app --factory

  # Mount multiple applications
  z main:app --mount /api:api:app --mount /admin:admin:app

  # Use a configuration file
  z myapp:app -c z.conf.py

For more information, visit: https://github.com/i2y/z
        """,
    )

    # Positional argument
    parser.add_argument(
        "app",
        help="Application module in format 'module:attribute' (e.g., 'myapp:app')",
    )

    # Core server settings
    server_group = parser.add_argument_group("Server Settings")
    server_group.add_argument(
        "-b",
        "--bind",
        default="0.0.0.0:8000",
        help="Bind address in format 'host:port' or 'unix:/path/to/socket' (default: 0.0.0.0:8000)",
    )
    server_group.add_argument(
        "--uds",
        help="Unix domain socket path (e.g., /tmp/z.sock)",
    )
    server_group.add_argument(
        "--fd",
        type=int,
        help="File descriptor for systemd socket activation (e.g., 3)",
    )
    server_group.add_argument(
        "-w",
        "--workers",
        type=int,
        help="Number of worker processes (default: auto-detect based on CPU cores)",
    )
    server_group.add_argument(
        "--threads",
        type=int,
        default=2,
        help="Blocking threads per worker (default: 2)",
    )
    server_group.add_argument(
        "--tokio-threads",
        type=int,
        help="Tokio I/O threads for Rust runtime (default: 1, optimal for HTTP/1.1)",
    )

    # Worker management
    worker_group = parser.add_argument_group("Worker Management")
    worker_group.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Worker timeout in seconds (Gunicorn-compatible, default: 30)",
    )
    worker_group.add_argument(
        "--graceful-timeout",
        type=int,
        default=30,
        help="Graceful shutdown timeout in seconds (default: 30)",
    )
    worker_group.add_argument(
        "--keepalive",
        type=int,
        default=5,
        help="HTTP Keep-Alive timeout in seconds (Gunicorn-compatible, default: 5)",
    )
    worker_group.add_argument(
        "--max-requests",
        type=int,
        help="Max requests per worker before restart (Gunicorn-compatible, not implemented)",
    )
    worker_group.add_argument(
        "--max-requests-jitter",
        type=int,
        help="Random jitter for max_requests (Gunicorn-compatible, not implemented)",
    )
    worker_group.add_argument(
        "--enable-restart",
        action="store_true",
        default=True,
        help="Enable auto-restart of crashed workers (default: enabled)",
    )
    worker_group.add_argument(
        "--no-restart",
        dest="enable_restart",
        action="store_false",
        help="Disable auto-restart of crashed workers",
    )
    worker_group.add_argument(
        "--max-restarts",
        type=int,
        default=5,
        help="Maximum restart attempts per worker (default: 5)",
    )
    worker_group.add_argument(
        "--worker-connections",
        type=int,
        default=1000,
        help="Max simultaneous clients per worker (Gunicorn-compatible, not implemented)",
    )
    worker_group.add_argument(
        "--limit-concurrency",
        type=int,
        help="Max concurrent connections (Uvicorn-compatible, not implemented)",
    )
    worker_group.add_argument(
        "--backlog",
        type=int,
        default=2048,
        help="Socket listen backlog (default: 2048)",
    )

    # Process management
    process_group = parser.add_argument_group("Process Management")
    process_group.add_argument(
        "-D",
        "--daemon",
        action="store_true",
        help="Run server in background (not implemented yet)",
    )
    process_group.add_argument("-p", "--pid", dest="pid_file", help="PID file location")
    process_group.add_argument(
        "--chdir", help="Change to directory before loading application"
    )

    # Application loading
    app_group = parser.add_argument_group("Application Loading")
    app_group.add_argument(
        "--factory",
        action="store_true",
        help="Treat application as a factory function that returns WSGI/ASGI app",
    )
    app_group.add_argument(
        "--app-dir", help="Add directory to PYTHONPATH for application import"
    )
    app_group.add_argument(
        "--mount",
        action="append",
        dest="mounts",
        help="Mount additional application at path (format: 'path:module:attr'). Can be used multiple times.",
    )

    # Logging
    logging_group = parser.add_argument_group("Logging")
    logging_group.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )
    logging_group.add_argument(
        "--log-format",
        choices=["text", "json"],
        help="Logging format (default: text)",
    )
    logging_group.add_argument(
        "--access-log",
        action="store_true",
        default=True,
        help="Enable access logging (default: enabled)",
    )
    logging_group.add_argument(
        "--no-access-log",
        dest="access_log",
        action="store_false",
        help="Disable access logging",
    )
    logging_group.add_argument(
        "--use-colors",
        action="store_true",
        default=None,
        help="Use colored log output (auto-detected by default)",
    )
    logging_group.add_argument(
        "--no-color",
        dest="use_colors",
        action="store_false",
        help="Disable colored log output",
    )
    logging_group.add_argument(
        "--error-log", help="Error log file (use '-' for stderr, not implemented yet)"
    )

    # Development options
    dev_group = parser.add_argument_group("Development")
    dev_group.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload on code changes (development only)",
    )
    dev_group.add_argument(
        "--reload-dir",
        action="append",
        dest="reload_dirs",
        help="Directory to watch for changes (can be used multiple times)",
    )
    dev_group.add_argument(
        "--reload-delay",
        type=float,
        default=0.25,
        help="Delay between reload checks in seconds (Uvicorn-compatible, default: 0.25)",
    )
    dev_group.add_argument(
        "--reload-include",
        action="append",
        dest="reload_includes",
        help="File pattern to include in reload watch (e.g., '*.py')",
    )
    dev_group.add_argument(
        "--reload-exclude",
        action="append",
        dest="reload_excludes",
        help="File pattern to exclude from reload watch (e.g., '.git/*')",
    )

    # Event Loop (Uvicorn compatibility)
    loop_group = parser.add_argument_group("Event Loop")
    loop_group.add_argument(
        "--loop",
        choices=["auto", "asyncio", "uvloop"],
        default="auto",
        help="Event loop implementation for ASGI apps (Uvicorn-compatible, default: auto/asyncio)",
    )

    # SSL/TLS
    ssl_group = parser.add_argument_group("SSL/TLS (Not yet implemented)")
    ssl_group.add_argument(
        "--ssl-keyfile",
        help="SSL key file path (not implemented)",
    )
    ssl_group.add_argument(
        "--ssl-certfile",
        help="SSL certificate file path (not implemented)",
    )
    ssl_group.add_argument(
        "--ssl-keyfile-password",
        help="Password for encrypted SSL key (not implemented)",
    )
    ssl_group.add_argument(
        "--ssl-ca-certs",
        help="CA certificates file for client verification (not implemented)",
    )

    # Configuration
    config_group = parser.add_argument_group("Configuration")
    config_group.add_argument(
        "-c", "--config", help="Configuration file path (Python format)"
    )
    config_group.add_argument(
        "--print-config",
        action="store_true",
        help="Print resolved configuration and exit",
    )
    config_group.add_argument(
        "--check-config",
        action="store_true",
        help="Validate configuration and exit",
    )

    # Utility
    parser.add_argument("-v", "--version", action="version", version=f"Z {__version__}")

    return parser


def resolve_config(args: argparse.Namespace) -> dict[str, Any]:
    """
    Resolve configuration from multiple sources.

    Priority order (highest to lowest):
    1. Command-line arguments
    2. Configuration file
    3. Environment variables
    4. Defaults

    Args:
        args: Parsed command-line arguments

    Returns:
        Resolved configuration dictionary

    Raises:
        ConfigError: If configuration is invalid
    """
    # 1. Get default config (empty, defaults are in argparse)
    default_config = {}

    # 2. Get environment config
    env_config = get_env_config()

    # 3. Load config file if specified
    file_config = {}
    if args.config:
        try:
            file_config = load_config_file(args.config)
            file_config = normalize_config(file_config)
        except ConfigError as e:
            print(f"Error loading config file: {e}", file=sys.stderr)
            sys.exit(1)

    # 4. Get CLI config (only explicitly provided values, not defaults)
    cli_config = {}

    # Get the parser defaults to compare against
    parser_temp = create_parser()
    defaults = vars(
        parser_temp.parse_args([args.app])
    )  # Parse with just the app argument to get defaults

    for key, value in vars(args).items():
        if value is not None and key not in [
            "config",
            "print_config",
            "check_config",
            "app",
        ]:
            # Only include if value differs from default (i.e., was explicitly set)
            if key not in defaults or defaults[key] != value:
                # Map CLI argument names to config keys
                if key == "max_restarts":
                    cli_config["max_restarts_per_worker"] = value
                elif key == "enable_restart":
                    cli_config["enable_worker_restart"] = value
                else:
                    cli_config[key] = value

    # Merge configs (later overrides earlier)
    config = merge_configs(default_config, env_config, file_config, cli_config)

    # Add the app module (always from CLI)
    config["app_module"] = args.app

    return config


def main() -> None:
    """
    Main entry point for the Qilin CLI.

    This function:
    1. Parses command-line arguments
    2. Resolves configuration from multiple sources
    3. Validates configuration
    4. Runs the application server

    Exit codes:
        0: Success
        1: Error (configuration, application loading, etc.)
        130: Interrupted by user (Ctrl+C)
    """
    parser = create_parser()
    args = parser.parse_args()

    # Handle --daemon (not implemented)
    if args.daemon:
        print("Error: --daemon mode is not implemented yet", file=sys.stderr)
        sys.exit(1)

    # Resolve configuration
    try:
        config = resolve_config(args)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    # Handle --print-config
    if args.print_config:
        print("Resolved configuration:")
        for key, value in sorted(config.items()):
            print(f"  {key}: {value}")
        sys.exit(0)

    # Validate configuration
    try:
        validate_config(config)
    except ConfigError as e:
        print(f"Configuration validation error: {e}", file=sys.stderr)
        sys.exit(1)

    # Handle --check-config
    if args.check_config:
        print("Configuration is valid")
        sys.exit(0)

    # Extract app_module and remove from config
    app_module = config.pop("app_module")

    # Extract reload settings
    reload = config.pop("reload", False)
    reload_dirs = config.pop("reload_dirs", None)
    reload_includes = config.pop("reload_includes", None)
    reload_excludes = config.pop("reload_excludes", None)

    # Extract logging settings
    access_log = config.pop("access_log", True)
    use_colors = config.pop("use_colors", None)

    # Set up access logging
    from ..access_log import setup_access_logging

    setup_access_logging(
        enabled=access_log, use_colors=use_colors if use_colors is not None else True
    )

    # Remove utility flags from config
    config.pop("daemon", None)
    config.pop("error_log", None)

    # Run the application
    try:
        if reload:
            # Run with auto-reload
            from ..reload import run_with_reload

            run_with_reload(
                target=run_application,
                args=(app_module,),
                kwargs=config,
                reload_dirs=reload_dirs,
                reload_includes=reload_includes,
                reload_excludes=reload_excludes,
            )
        else:
            # Run normally
            run_application(app_module, **config)
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
