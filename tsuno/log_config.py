"""
Logging configuration for tsuno.

Provides Uvicorn-compatible logging configuration with support for
custom log configs via dictConfig.
"""

import logging
import logging.config
from typing import Any

# Default logging configuration (Uvicorn-compatible)
DEFAULT_LOG_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "logging.Formatter",
            "fmt": "%(levelname)s:     %(message)s",
            "use_colors": None,
        },
        "access": {
            "()": "tsuno.access_log.AccessLogFormatter",
            "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "tsuno": {"handlers": ["default"], "level": "INFO"},
        "tsuno.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
    },
}


def setup_logging(
    log_level: str | None = None,
    log_config: dict[str, Any] | None = None,
    access_log: bool = True,
    use_colors: bool | None = None,
) -> None:
    """
    Set up logging configuration.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_config: Custom logging configuration dict (dictConfig format)
        access_log: Enable access logging
        use_colors: Enable colored output (auto-detected if None)
    """
    # Use custom config if provided
    if log_config:
        logging.config.dictConfig(log_config)
        return

    # Use default config
    config = DEFAULT_LOG_CONFIG.copy()

    # Set log level
    if log_level:
        level = log_level.upper()
        config["loggers"]["tsuno"]["level"] = level

    # Configure access logging
    if not access_log:
        config["loggers"]["tsuno.access"]["handlers"] = []

    # Configure colors in formatters
    if use_colors is not None:
        if "default" in config["formatters"]:
            config["formatters"]["default"]["use_colors"] = use_colors
        if "access" in config["formatters"]:
            config["formatters"]["access"]["use_colors"] = use_colors

    # Apply configuration
    logging.config.dictConfig(config)


def load_log_config_file(config_file: str) -> dict[str, Any]:
    """
    Load logging configuration from a file.

    Supports:
    - Python files (.py) with LOG_CONFIG variable
    - JSON files (.json)
    - YAML files (.yaml, .yml) if PyYAML is installed

    Args:
        config_file: Path to configuration file

    Returns:
        Logging configuration dictionary

    Raises:
        ValueError: If file format is not supported
        FileNotFoundError: If file does not exist
    """
    import os

    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Log config file not found: {config_file}")

    # Python file
    if config_file.endswith(".py"):
        import importlib.util

        spec = importlib.util.spec_from_file_location("log_config", config_file)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "LOG_CONFIG"):
                return module.LOG_CONFIG
            else:
                raise ValueError(
                    f"Python config file must define LOG_CONFIG variable: {config_file}"
                )
        else:
            raise ValueError(f"Failed to load Python config file: {config_file}")

    # JSON file
    elif config_file.endswith(".json"):
        import json

        with open(config_file, "r") as f:
            return json.load(f)

    # YAML file
    elif config_file.endswith((".yaml", ".yml")):
        try:
            import yaml

            with open(config_file, "r") as f:
                return yaml.safe_load(f)
        except ImportError:
            raise ValueError("PyYAML is not installed. Install it with: pip install pyyaml")

    else:
        raise ValueError(
            f"Unsupported log config file format: {config_file}. "
            "Supported formats: .py, .json, .yaml, .yml"
        )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
