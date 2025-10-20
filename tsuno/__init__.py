"""
tsuno: WSGI/ASGI server powered by Rust
"""

from typing import Any, Callable

from .asgi_adapter import ASGIAdapter
from .asgi_event_loop_worker import ASGIEventLoopWorker
from .constants import HttpVersion
from .dispatcher import Dispatcher
from .unified_server import serve, serve_fd, serve_uds
from .wsgi_adapter import WSGIAdapter

__all__ = [
    # Main API
    "run",
    # Server functions
    "serve",
    "serve_fd",
    "serve_uds",
    # Adapters
    "WSGIAdapter",
    "ASGIAdapter",
    "ASGIEventLoopWorker",
    # Dispatcher
    "Dispatcher",
    # Constants
    "HttpVersion",
]

__version__ = "0.1.0"


def run(
    app: str | Callable | dict[str, Any],
    # Binding Options (Gunicorn/Uvicorn compatible)
    host: str = "127.0.0.1",
    port: int = 8000,
    bind: str | None = None,
    uds: str | None = None,
    fd: int | None = None,
    # Worker Configuration
    workers: int | None = None,
    worker_class: str = "sync",  # Gunicorn: sync/async/gthread/gevent/eventlet
    threads: int | None = None,  # Gunicorn: threads per worker (alias for blocking_threads)
    worker_connections: int = 1000,  # Gunicorn: max simultaneous clients per worker
    # tsuno-specific: Performance Tuning
    blocking_threads: int = 2,
    tokio_threads: int | None = None,
    # Worker Management (tsuno + Gunicorn)
    enable_worker_restart: bool = True,
    max_restarts_per_worker: int = 5,
    timeout: int = 30,
    graceful_timeout: int = 30,
    # Process Management
    pid_file: str | None = None,
    pid: str | None = None,  # Gunicorn alias for pid_file
    daemon: bool = False,  # Gunicorn: daemonize the process
    user: str | None = None,  # Gunicorn: switch to user
    group: str | None = None,  # Gunicorn: switch to group
    umask: int | None = None,  # Gunicorn: file creation mask
    # Logging (Uvicorn/Gunicorn compatible)
    log_level: str | None = None,
    loglevel: str | None = None,  # Gunicorn alias for log_level
    log_format: str | None = None,
    access_log: bool = True,
    accesslog: str | None = None,  # Gunicorn: access log file path
    errorlog: str | None = None,  # Gunicorn: error log file path
    use_colors: bool | None = None,
    log_config: dict | str | None = None,
    # Development (Uvicorn compatible)
    reload: bool = False,
    reload_dirs: list | None = None,
    reload_dir: str | None = None,  # Uvicorn alias (single dir)
    reload_delay: float = 0.25,  # Uvicorn: delay between reload checks
    reload_includes: list | None = None,
    reload_excludes: list | None = None,
    # Gunicorn additional parameters
    keepalive: int = 5,
    max_requests: int | None = None,
    max_requests_jitter: int | None = None,
    preload_app: bool = False,  # Gunicorn: load app before forking
    # Uvicorn additional parameters
    backlog: int = 2048,
    limit_concurrency: int | None = None,
    limit_max_requests: int | None = None,  # Uvicorn alias for max_requests
    timeout_keep_alive: int | None = None,  # Uvicorn alias for keepalive
    timeout_graceful_shutdown: int | None = None,  # Uvicorn alias for graceful_timeout
    timeout_worker_healthcheck: int | None = None,  # Uvicorn alias for timeout
    root_path: str = "",
    app_dir: str | None = None,
    # Proxy & Headers (Uvicorn)
    forwarded_allow_ips: str | None = None,  # Uvicorn: trusted proxy IPs
    proxy_headers: bool = True,  # Uvicorn: enable X-Forwarded-* headers
    server_header: bool = True,  # Uvicorn: enable Server header
    date_header: bool = True,  # Uvicorn: enable Date header
    headers: list | None = None,  # Uvicorn: custom default headers
    # SSL/TLS (Uvicorn/Gunicorn)
    ssl_keyfile: str | None = None,  # Uvicorn/Gunicorn: SSL private key
    ssl_certfile: str | None = None,  # Uvicorn/Gunicorn: SSL certificate
    keyfile: str | None = None,  # Gunicorn alias for ssl_keyfile
    certfile: str | None = None,  # Gunicorn alias for ssl_certfile
    ssl_keyfile_password: str | None = None,  # Uvicorn: password for encrypted key
    ssl_version: int = 17,  # Uvicorn: SSL version (TLSv1.2 by default)
    ssl_cert_reqs: int = 0,  # Uvicorn: client cert requirements
    ssl_ca_certs: str | None = None,  # Uvicorn: CA certs file
    ssl_ciphers: str = "TLSv1",  # Uvicorn: allowed cipher suites
    # Protocol Options (Uvicorn) - Most not applicable to tsuno
    loop: str = "auto",  # Uvicorn: event loop (asyncio/uvloop) - NOT APPLICABLE (using Rust)
    use_uvloop: bool = False,  # tsuno: Enable uvloop for application-level I/O (ASGI only)
    http: str = "auto",  # Uvicorn: HTTP impl (h11/httptools) - NOT APPLICABLE (using Hyper)
    ws: str = "auto",  # Uvicorn: WebSocket impl - NOT APPLICABLE
    ws_max_size: int = 16777216,  # Uvicorn: max WS message size - NOT APPLICABLE
    ws_max_queue: int = 32,  # Uvicorn: WS queue length - NOT APPLICABLE
    ws_ping_interval: float = 20.0,  # Uvicorn: WS ping interval - NOT APPLICABLE
    ws_ping_timeout: float = 20.0,  # Uvicorn: WS ping timeout - NOT APPLICABLE
    ws_per_message_deflate: bool = True,  # Uvicorn: WS compression - NOT APPLICABLE
    lifespan: str = "auto",  # Uvicorn: lifespan protocol - ALREADY IMPLEMENTED
    h11_max_incomplete_event_size: int = 16384,  # Uvicorn: HTTP parser buffer - NOT APPLICABLE
    # Other
    factory: bool = False,
    interface: str = "auto",
    **kwargs: Any,
):
    """
    Run WSGI/ASGI application with Tsuno server.

    This is the unified API that accepts parameters from Uvicorn, Gunicorn, and tsuno-specific options.

    Args:
        app: Application instance, import string, or dictionary of apps
        host: Host to bind to (default: "127.0.0.1")
        port: Port to bind to (default: 8000)
        bind: Gunicorn-style bind address (alternative to host:port, e.g., "0.0.0.0:8000")
        uds: Unix domain socket path (e.g., "/tmp/tsuno.sock")
        fd: File descriptor for systemd socket activation
        workers: Number of worker processes (default: auto-detect)
        blocking_threads: Python blocking threads per worker (tsuno-specific, default: 2)
        tokio_threads: Tokio I/O threads (tsuno-specific, default: 1, optimal for HTTP/1.1)
        enable_worker_restart: Auto-restart crashed workers (tsuno-specific, default: True)
        max_restarts_per_worker: Max restart attempts (tsuno-specific, default: 5)
        timeout: Worker timeout in seconds (Gunicorn-compatible, default: 30)
        graceful_timeout: Graceful shutdown timeout (default: 30)
        pid_file: PID file path for process management
        log_level: Logging level (DEBUG/INFO/WARNING/ERROR)
        log_format: Logging format (text/json)
        access_log: Enable access logging (Uvicorn-compatible, default: True)
        use_colors: Use colored logs (Uvicorn-compatible, auto-detect)
        log_config: Logging configuration dict or file path
        reload: Enable auto-reload on code changes (Uvicorn-compatible, default: False)
        reload_dirs: Directories to watch for reload
        reload_includes: File patterns to include in reload
        reload_excludes: File patterns to exclude from reload
        keepalive: Keep-alive timeout (Gunicorn-compatible, default: 5)
        max_requests: Max requests per worker (Gunicorn-compatible)
        max_requests_jitter: Jitter for max_requests (Gunicorn-compatible)
        factory: Treat app as factory function (default: False)
        interface: Application interface (auto/asgi/wsgi)
        **kwargs: Additional parameters (for compatibility)

    Examples:
        # Simple usage (Uvicorn-style)
        run(app, host="0.0.0.0", port=8000)

        # Gunicorn-style with bind
        run(app, bind="0.0.0.0:8000", workers=4)

        # tsuno-specific performance tuning
        run(app, bind="0.0.0.0:8000", blocking_threads=2, tokio_threads=3)

        # Unix domain socket
        run(app, uds="/tmp/tsuno.sock")

        # File descriptor (systemd)
        run(app, fd=3)

        # Development with reload
        run(app, reload=True, reload_dirs=["./myapp"])

        # Production with PID file
        run(app, bind="0.0.0.0:8000", workers=4, pid_file="/var/run/tsuno.pid")
    """
    import warnings

    # Handle parameter aliases
    # Uvicorn aliases
    if limit_max_requests is not None and max_requests is None:
        max_requests = limit_max_requests
    if timeout_keep_alive is not None and keepalive == 5:
        keepalive = timeout_keep_alive
    if timeout_graceful_shutdown is not None and graceful_timeout == 30:
        graceful_timeout = timeout_graceful_shutdown
    if timeout_worker_healthcheck is not None and timeout == 30:
        timeout = timeout_worker_healthcheck
    if reload_dir is not None and reload_dirs is None:
        reload_dirs = [reload_dir]

    # Gunicorn aliases
    if pid is not None and pid_file is None:
        pid_file = pid
    if loglevel is not None and log_level is None:
        log_level = loglevel
    if keyfile is not None and ssl_keyfile is None:
        ssl_keyfile = keyfile
    if certfile is not None and ssl_certfile is None:
        ssl_certfile = certfile
    if threads is not None and blocking_threads == 2:
        blocking_threads = threads

    # Handle loop parameter (Uvicorn compatibility)
    # Convert loop="uvloop" to use_uvloop=True
    if loop == "uvloop":
        use_uvloop = True
    elif loop == "asyncio":
        use_uvloop = False
    elif loop == "auto":
        # Auto-detect: use uvloop if available (Uvicorn behavior)
        try:
            import uvloop  # noqa: F401

            use_uvloop = True
        except ImportError:
            use_uvloop = False
    else:
        # Unknown loop value, warn and use default
        warnings.warn(
            f"Unknown loop value '{loop}'. Valid values are 'auto', 'asyncio', 'uvloop'. "
            f"Using default (auto-detect).",
            UserWarning,
            stacklevel=2,
        )
        # Try auto-detect for unknown values too
        try:
            import uvloop  # noqa: F401

            use_uvloop = True
        except ImportError:
            use_uvloop = False

    # Warn about not-applicable parameters
    not_applicable_params = {
        "http": http != "auto",
        "ws": ws != "auto",
        "ws_max_size": ws_max_size != 16777216,
        "ws_max_queue": ws_max_queue != 32,
        "ws_ping_interval": ws_ping_interval != 20.0,
        "ws_ping_timeout": ws_ping_timeout != 20.0,
        "ws_per_message_deflate": ws_per_message_deflate is not True,
        "h11_max_incomplete_event_size": h11_max_incomplete_event_size != 16384,
    }

    for param, is_custom in not_applicable_params.items():
        if is_custom:
            warnings.warn(
                f"Parameter '{param}' is not applicable to Tsuno (uses Rust/Hyper transport). "
                f"Parameter will be ignored.",
                UserWarning,
                stacklevel=2,
            )

    # Warn about not-yet-implemented parameters
    not_implemented = []
    # daemon, user, group, umask are now implemented
    if worker_class != "sync":
        not_implemented.append("worker_class")
    if worker_connections != 1000:
        not_implemented.append("worker_connections")
    # preload_app is effectively always enabled (apps are loaded before fork)
    # limit_concurrency is now implemented in Rust layer
    # Parse forwarded_allow_ips (comma-separated string -> list)
    forwarded_allow_ips_list = None
    if forwarded_allow_ips:
        forwarded_allow_ips_list = [ip.strip() for ip in forwarded_allow_ips.split(",")]
    if not proxy_headers:
        not_implemented.append("proxy_headers=False")
    # server_header, date_header, headers: accepted but not customizable yet (use defaults)
    if ssl_keyfile is not None or ssl_certfile is not None:
        not_implemented.append("SSL/TLS")
    # max_requests, max_requests_jitter, timeout, reload_delay are now implemented

    if not_implemented:
        warnings.warn(
            f"The following parameters are not yet implemented and will be ignored: "
            f"{', '.join(not_implemented)}. "
            f"See https://github.com/i2y/tsuno/issues for implementation status.",
            UserWarning,
            stacklevel=2,
        )

    # Add app_dir to Python path if specified
    if app_dir is not None:
        import sys

        sys.path.insert(0, app_dir)

    # Setup access logging
    from .access_log import setup_access_logging  # type: ignore

    setup_access_logging(
        enabled=access_log, use_colors=use_colors if use_colors is not None else True
    )

    # Setup logging configuration
    if log_config is not None:
        from .log_config import load_log_config_file, setup_logging  # type: ignore

        if isinstance(log_config, dict):
            setup_logging(log_config)  # type: ignore
        elif isinstance(log_config, str):
            config = load_log_config_file(log_config)  # type: ignore
            setup_logging(config)  # type: ignore

    # Load environment file if specified (Uvicorn compatibility)
    env_file = kwargs.get("env_file")
    if env_file:
        from dotenv import load_dotenv

        load_dotenv(env_file)

    # Convert app to dictionary format if needed
    if isinstance(app, dict):
        apps = app
    elif isinstance(app, str):
        # Import string format "module:attribute"
        from .cli.utils import import_app

        app_instance = import_app(app, factory=factory)
        apps = {"/": app_instance}
    else:
        # Direct application instance
        apps = {"/": app}

    # Determine binding method (priority: fd > uds > bind > host:port)
    if fd is not None:
        # File descriptor mode (systemd socket activation)
        serve_fd(
            apps=apps,
            fd=fd,
            blocking_threads=blocking_threads,
            tokio_threads=tokio_threads,
            log_level=log_level,
            log_format=log_format,
        )
    elif uds is not None:
        # Unix domain socket mode
        serve_uds(
            apps=apps,
            socket_path=uds,
            blocking_threads=blocking_threads,
            tokio_threads=tokio_threads,
            log_level=log_level,
            log_format=log_format,
        )
    else:
        # TCP socket mode (standard)
        # Parse bind parameter if provided (Gunicorn-style)
        if bind is not None:
            if ":" in bind:
                host, port_str = bind.rsplit(":", 1)
                port = int(port_str)
            else:
                # Unix socket in bind format (e.g., "unix:/tmp/tsuno.sock")
                if bind.startswith("unix:"):
                    uds_path = bind[5:]  # Remove "unix:" prefix
                    serve_uds(
                        apps=apps,
                        socket_path=uds_path,
                        blocking_threads=blocking_threads,
                        tokio_threads=tokio_threads,
                        log_level=log_level,
                        log_format=log_format,
                    )
                    return
                else:
                    raise ValueError(f"Invalid bind format: {bind}")

        address = f"{host}:{port}"

        # Run with reload if requested
        if reload:
            from .reload import run_with_reload

            run_with_reload(
                target=serve,
                args=(),
                kwargs={
                    "apps": apps,
                    "address": address,
                    "workers": workers,
                    "blocking_threads": blocking_threads,
                    "tokio_threads": tokio_threads,
                    "enable_worker_restart": enable_worker_restart,
                    "max_restarts_per_worker": max_restarts_per_worker,
                    "graceful_timeout": graceful_timeout,
                    "pid_file": pid_file,
                    "log_level": log_level,
                    "log_format": log_format,
                    "timeout": timeout,
                    "keepalive": keepalive,
                    "max_requests": max_requests,
                    "max_requests_jitter": max_requests_jitter,
                    "backlog": backlog,
                    "limit_concurrency": limit_concurrency,
                    "root_path": root_path,
                    "accesslog": accesslog,
                    "errorlog": errorlog,
                    "access_log": access_log,
                    "use_colors": use_colors,
                    "forwarded_allow_ips": forwarded_allow_ips_list,
                    "user": user,
                    "group": group,
                    "umask": umask,
                    "daemon": daemon,
                },
                reload_dirs=reload_dirs,
                reload_includes=reload_includes,
                reload_excludes=reload_excludes,
                reload_delay=reload_delay,
            )
        else:
            # Normal mode
            serve(
                apps=apps,
                address=address,
                workers=workers,
                blocking_threads=blocking_threads,
                tokio_threads=tokio_threads,
                enable_worker_restart=enable_worker_restart,
                max_restarts_per_worker=max_restarts_per_worker,
                graceful_timeout=graceful_timeout,
                pid_file=pid_file,
                log_level=log_level,
                log_format=log_format,
                timeout=timeout,
                keepalive=keepalive,
                max_requests=max_requests,
                max_requests_jitter=max_requests_jitter,
                backlog=backlog,
                limit_concurrency=limit_concurrency,
                root_path=root_path,
                use_uvloop=use_uvloop,
                accesslog=accesslog,
                errorlog=errorlog,
                access_log=access_log,
                use_colors=use_colors,
                forwarded_allow_ips=forwarded_allow_ips_list,
                user=user,
                group=group,
                umask=umask,
                daemon=daemon,
            )
