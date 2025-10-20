"""
Configuration handling for tsuno CLI.

This module handles loading and merging configuration from:
1. Default values
2. Environment variables
3. Configuration files (Python or TOML format)
4. Command-line arguments
"""

import os
import tomllib
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """Raised when configuration is invalid."""

    pass


def load_python_config_file(config_path: str) -> dict[str, Any]:
    """
    Load configuration from a Python file.

    The config file is executed as Python code and variables
    defined in it are extracted as configuration settings.

    Args:
        config_path: Path to configuration file

    Returns:
        Dictionary of configuration settings

    Raises:
        ConfigError: If config file cannot be loaded

    Example config file (tsuno.conf.py):
        bind = "0.0.0.0:8000"
        workers = 4
        threads = 2
        loglevel = "info"
    """
    cp = Path(config_path)

    if not cp.exists():
        raise ConfigError(f"Configuration file not found: {cp}")

    if not cp.is_file():
        raise ConfigError(f"Configuration path is not a file: {cp}")

    # Execute the config file
    config_globals = {}
    config_locals = {}

    try:
        with open(cp, "r") as f:
            code = compile(f.read(), str(cp), "exec")
            exec(code, config_globals, config_locals)
    except Exception as e:
        raise ConfigError(f"Error executing config file '{cp}': {e}") from e

    # Extract configuration (exclude built-ins and imports)
    config = {}

    # Gunicorn-compatible hook functions (16 hooks)
    hook_names = [
        # Master process hooks
        "on_starting",
        "on_reload",
        "when_ready",
        "on_exit",
        # Worker lifecycle hooks
        "pre_fork",
        "post_fork",
        "post_worker_init",
        "child_exit",
        "worker_exit",
        # Signal hooks
        "worker_int",
        "worker_abort",
        # Workers changed
        "nworkers_changed",
        # Request hooks
        "pre_request",
        "post_request",
        # Advanced hooks
        "pre_exec",
        "ssl_context",
    ]

    for key, value in config_locals.items():
        if not key.startswith("_") and not callable(value) or key in hook_names:
            config[key] = value

    return config


def load_toml_config_file(config_path: str) -> dict[str, Any]:
    """
    Load configuration from a TOML file.

    Args:
        config_path: Path to TOML configuration file

    Returns:
        Dictionary of configuration settings

    Raises:
        ConfigError: If config file cannot be loaded

    Example config file (tsuno.toml):
        bind = "0.0.0.0:8000"
        workers = 4
        threads = 2
        log_level = "info"
    """
    cp = Path(config_path)

    if not cp.exists():
        raise ConfigError(f"Configuration file not found: {cp}")

    if not cp.is_file():
        raise ConfigError(f"Configuration path is not a file: {cp}")

    try:
        with open(cp, "rb") as f:
            config = tomllib.load(f)

        # Flatten nested sections if needed (e.g., [server] section)
        # TOML allows nested structures, extract relevant config
        flattened = {}
        for key, value in config.items():
            if isinstance(value, dict):
                # Flatten nested sections
                flattened.update(value)
            else:
                flattened[key] = value

        return flattened

    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Error parsing TOML config file '{cp}': {e}") from e
    except Exception as e:
        raise ConfigError(f"Error loading TOML config file '{cp}': {e}") from e


def load_config_file(config_path: str) -> dict[str, Any]:
    """
    Load configuration from a file (Python or TOML format).

    File format is auto-detected based on extension:
    - .toml: TOML format
    - .py: Python format

    Args:
        config_path: Path to configuration file

    Returns:
        Dictionary of configuration settings

    Raises:
        ConfigError: If config file cannot be loaded

    Example usage:
        # Python format
        config = load_config_file("tsuno.conf.py")

        # TOML format
        config = load_config_file("tsuno.toml")
    """
    cp = Path(config_path)

    if not cp.exists():
        raise ConfigError(f"Configuration file not found: {cp}")

    # Auto-detect format based on extension
    match cp.suffix.lower():
        case ".toml":
            return load_toml_config_file(str(cp))
        case ".py":
            return load_python_config_file(str(cp))
        case _:
            # Try to detect format by content
            try:
                with open(cp, "rb") as f:
                    first_bytes = f.read(100)
                    # Check for TOML-like syntax
                    if b"[" in first_bytes or (b"=" in first_bytes and b"\n" in first_bytes):
                        # Try TOML first
                        try:
                            return load_toml_config_file(str(cp))
                        except ConfigError:
                            # Fall back to Python
                            return load_python_config_file(str(cp))
                    else:
                        # Default to Python
                        return load_python_config_file(str(cp))
            except Exception:
                # If all else fails, try Python format
                return load_python_config_file(str(cp))


def merge_configs(*configs: dict[str, Any]) -> dict[str, Any]:
    """
    Merge multiple configuration dictionaries.

    Later dictionaries override earlier ones.

    Args:
        *configs: Configuration dictionaries to merge

    Returns:
        Merged configuration dictionary
    """
    result = {}
    for config in configs:
        if config:
            result.update(config)
    return result


def get_env_config() -> dict[str, Any]:
    """
    Extract configuration from environment variables.

    Supported environment variables:
    - LOG_LEVEL: Python logging level
    - LOG_FORMAT: Python logging format (text/json)
    - TOKIO_WORKER_THREADS: Tokio runtime threads
    - IO_WORKER_THREADS: Alternative name for Tokio threads

    Returns:
        Dictionary of configuration from environment
    """
    config = {}

    # Python logging
    if log_level := os.getenv("LOG_LEVEL"):
        config["log_level"] = log_level

    if log_format := os.getenv("LOG_FORMAT"):
        config["log_format"] = log_format

    # Tokio threads (Rust side)
    if tokio_threads := os.getenv("TOKIO_WORKER_THREADS"):
        try:
            config["tokio_threads"] = int(tokio_threads)
        except ValueError:
            pass

    if "tokio_threads" not in config:
        if io_threads := os.getenv("IO_WORKER_THREADS"):
            try:
                config["tokio_threads"] = int(io_threads)
            except ValueError:
                pass

    return config


def normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize configuration keys and values.

    This handles variations in naming (e.g., 'loglevel' -> 'log_level').

    Args:
        config: Raw configuration dictionary

    Returns:
        Normalized configuration dictionary
    """
    normalized = {}

    # Mapping of config file names to internal names (Gunicorn/Uvicorn compatible)
    key_mapping = {
        # Logging (Gunicorn/Uvicorn compatible)
        "loglevel": "log_level",
        "logformat": "log_format",
        "accesslog": "access_log",
        "errorlog": "error_log",
        # Process management (Gunicorn compatible)
        "pidfile": "pid_file",
        "proc_name": "process_name",
        # Worker configuration (Gunicorn compatible)
        "worker_class": "interface",  # sync/async/gthread → wsgi/asgi
        "worker_connections": "limit_concurrency",
        # Timeouts (Gunicorn compatible aliases)
        "timeout_graceful_shutdown": "graceful_timeout",
        # Environment (Gunicorn compatible)
        "raw_env": "env_vars",
        # Uvicorn compatible aliases
        "timeout_keep_alive": "keepalive",
        "limit_max_requests": "max_requests",
    }

    for key, value in config.items():
        # Normalize key name
        normalized_key = key_mapping.get(key, key)
        normalized[normalized_key] = value

    return normalized


def validate_config(config: dict[str, Any]) -> None:
    """
    Validate configuration values.

    Args:
        config: Configuration dictionary to validate

    Raises:
        ConfigError: If configuration is invalid
    """
    # Validate workers
    if "workers" in config:
        workers = config["workers"]
        if not isinstance(workers, int) or workers < 1:
            raise ConfigError(f"workers must be a positive integer, got: {workers}")

    # Validate threads
    if "threads" in config:
        threads = config["threads"]
        if not isinstance(threads, int) or threads < 1:
            raise ConfigError(f"threads must be a positive integer, got: {threads}")

    # Validate tokio_threads
    if "tokio_threads" in config:
        tokio_threads = config["tokio_threads"]
        if not isinstance(tokio_threads, int) or tokio_threads < 1:
            raise ConfigError(f"tokio_threads must be a positive integer, got: {tokio_threads}")

    # Validate timeout
    if "timeout" in config:
        timeout = config["timeout"]
        if not isinstance(timeout, int) or timeout < 0:
            raise ConfigError(f"timeout must be a non-negative integer, got: {timeout}")

    # Validate graceful_timeout
    if "graceful_timeout" in config:
        graceful_timeout = config["graceful_timeout"]
        if not isinstance(graceful_timeout, int) or graceful_timeout < 0:
            raise ConfigError(
                f"graceful_timeout must be a non-negative integer, got: {graceful_timeout}"
            )

    # Validate max_restarts_per_worker
    if "max_restarts_per_worker" in config:
        max_restarts = config["max_restarts_per_worker"]
        if not isinstance(max_restarts, int) or max_restarts < 0:
            raise ConfigError(
                f"max_restarts_per_worker must be a non-negative integer, got: {max_restarts}"
            )

    # Validate log_level
    if "log_level" in config:
        log_level = config["log_level"].upper()
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if log_level not in valid_levels:
            raise ConfigError(
                f"log_level must be one of {valid_levels}, got: {config['log_level']}"
            )

    # Validate log_format
    if "log_format" in config:
        log_format = config["log_format"].lower()
        if log_format not in ["text", "json"]:
            raise ConfigError(f"log_format must be 'text' or 'json', got: {config['log_format']}")

    # Validate interface (worker_class)
    if "interface" in config:
        interface = config["interface"]
        valid_interfaces = ["wsgi", "asgi", "auto"]
        if interface not in valid_interfaces:
            raise ConfigError(f"interface must be one of {valid_interfaces}, got: {interface}")

    # Validate bind address
    if "bind" in config:
        bind = config["bind"]
        if not isinstance(bind, str):
            raise ConfigError(f"bind must be a string, got: {type(bind).__name__}")

    # Validate hook functions
    hook_names = [
        "on_starting",
        "on_reload",
        "when_ready",
        "on_exit",
        "pre_fork",
        "post_fork",
        "post_worker_init",
        "worker_int",
        "worker_abort",
        "child_exit",
        "worker_exit",
        "nworkers_changed",
        "pre_request",
        "post_request",
        "pre_exec",
        "ssl_context",
    ]
    for hook_name in hook_names:
        if hook_name in config:
            hook = config[hook_name]
            if not callable(hook):
                raise ConfigError(
                    f"{hook_name} must be a callable function, got: {type(hook).__name__}"
                )
