"""
Application runner for tsuno CLI.

This module handles loading and running applications with
the Tsuno server.
"""

import sys
from typing import Any

from tsuno import serve, serve_fd, serve_uds

from .utils import ApplicationLoadError, import_app, parse_mount_spec


def run_application(
    app_module: str,
    bind: str = "0.0.0.0:8000",
    uds: str | None = None,
    fd: int | None = None,
    workers: int | None = None,
    threads: int = 2,
    tokio_threads: int | None = None,
    timeout: int = 30,
    graceful_timeout: int = 30,
    enable_worker_restart: bool = True,
    max_restarts_per_worker: int = 5,
    pid_file: str | None = None,
    log_level: str | None = None,
    log_format: str | None = None,
    factory: bool = False,
    app_dir: str | None = None,
    mounts: list[str] | None = None,
    chdir: str | None = None,
) -> None:
    """
    Run application with Z server.

    Args:
        app_module: Application module string (e.g., "myapp:application")
        bind: Bind address (e.g., "0.0.0.0:8000" or "unix:/tmp/tsuno.sock")
        uds: Unix domain socket path (e.g., "/tmp/tsuno.sock")
        fd: File descriptor for systemd socket activation
        workers: Number of worker processes (auto-detect if None)
        threads: Blocking threads per worker
        tokio_threads: Tokio I/O threads
        timeout: Worker timeout in seconds
        graceful_timeout: Graceful shutdown timeout
        enable_worker_restart: Enable auto-restart of crashed workers
        max_restarts_per_worker: Max restart attempts per worker
        pid_file: PID file location
        log_level: Logging level
        log_format: Logging format
        factory: Treat app as factory function
        app_dir: Directory to add to PYTHONPATH
        mounts: List of additional mount specifications
        chdir: Change to directory before loading app

    Raises:
        ApplicationLoadError: If application cannot be loaded
        SystemExit: If server fails to start
    """
    # Change directory if requested
    if chdir:
        import os

        try:
            os.chdir(chdir)
            print(f"Changed working directory to: {chdir}", file=sys.stderr)
        except FileNotFoundError:
            print(f"Error: Directory not found: {chdir}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error changing directory to {chdir}: {e}", file=sys.stderr)
            sys.exit(1)

    # Build apps dictionary
    apps: dict[str, Any] = {}

    try:
        # Import main application
        main_app = import_app(app_module, factory=factory, app_dir=app_dir)
        apps["/"] = main_app

        # Import mounted applications if specified
        if mounts:
            for mount_spec in mounts:
                path, module_str = parse_mount_spec(mount_spec)
                mounted_app = import_app(module_str, factory=False, app_dir=app_dir)
                apps[path] = mounted_app
                print(f"Mounted application at {path}: {module_str}", file=sys.stderr)

    except ApplicationLoadError as e:
        print(f"Error loading application: {e}", file=sys.stderr)
        sys.exit(1)

    # Print startup message
    print("Starting Z server...", file=sys.stderr)
    print(f"Application: {app_module}", file=sys.stderr)

    # Determine binding method
    if fd is not None:
        print(f"File descriptor: {fd}", file=sys.stderr)
    elif uds is not None:
        print(f"Unix socket: {uds}", file=sys.stderr)
    else:
        print(f"Bind address: {bind}", file=sys.stderr)

    if workers is not None:
        print(f"Workers: {workers}", file=sys.stderr)
    else:
        print("Workers: auto-detect", file=sys.stderr)
    print(f"Threads per worker: {threads}", file=sys.stderr)
    if tokio_threads is not None:
        print(f"Tokio threads: {tokio_threads}", file=sys.stderr)
    print(f"Log level: {log_level or 'INFO'}", file=sys.stderr)
    print(f"Log format: {log_format or 'text'}", file=sys.stderr)
    print("", file=sys.stderr)

    # Run the server
    try:
        if fd is not None:
            # File descriptor mode (systemd socket activation)
            serve_fd(
                apps=apps,
                fd=fd,
                blocking_threads=threads,
                tokio_threads=tokio_threads,
                log_level=log_level,
                log_format=log_format,
            )
        elif uds is not None:
            # Unix domain socket mode
            serve_uds(
                apps=apps,
                socket_path=uds,
                blocking_threads=threads,
                tokio_threads=tokio_threads,
                log_level=log_level,
                log_format=log_format,
            )
        elif bind.startswith("unix:"):
            # Unix socket in bind format (Gunicorn-style)
            socket_path = bind[5:]  # Remove "unix:" prefix
            serve_uds(
                apps=apps,
                socket_path=socket_path,
                blocking_threads=threads,
                tokio_threads=tokio_threads,
                log_level=log_level,
                log_format=log_format,
            )
        else:
            # Standard TCP socket mode
            serve(
                apps=apps,
                address=bind,
                workers=workers,
                blocking_threads=threads,
                tokio_threads=tokio_threads,
                enable_worker_restart=enable_worker_restart,
                max_restarts_per_worker=max_restarts_per_worker,
                timeout=timeout,
                graceful_timeout=graceful_timeout,
                pid_file=pid_file,
                log_level=log_level,
                log_format=log_format,
            )
    except KeyboardInterrupt:
        print("\nShutting down...", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        sys.exit(1)
