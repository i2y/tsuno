"""
Multiprocess unified server for WSGI and ASGI applications.

This module provides high-performance multiprocess serving with dictionary-based
routing.
"""

from __future__ import annotations

import grp
import multiprocessing
import os
import pwd
import random
import signal
import socket
import sys
import time
from ctypes import c_double, c_int
from multiprocessing import Value
from typing import Any

import pyhtransport

from .access_log import setup_access_logging
from .dispatcher import Dispatcher
from .error_log import setup_error_logging


def _daemonize():
    """
    Daemonize the current process using the double-fork technique.

    This detaches the process from the controlling terminal and ensures it
    runs in the background as a proper daemon.

    Steps:
    1. First fork - parent exits, child continues
    2. Become session leader (setsid) - detach from controlling terminal
    3. Second fork - session leader exits, child continues as daemon
    4. Change working directory to root
    5. Redirect stdin/stdout/stderr to /dev/null

    Raises:
        OSError: If forking fails
    """
    # First fork
    try:
        pid = os.fork()
        if pid > 0:
            # Parent process - exit
            sys.exit(0)
    except OSError as e:
        raise OSError(f"First fork failed: {e}")

    # Decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(0)

    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            # Second parent - exit
            sys.exit(0)
    except OSError as e:
        raise OSError(f"Second fork failed: {e}")

    # Redirect standard file descriptors to /dev/null
    sys.stdout.flush()
    sys.stderr.flush()

    with open("/dev/null", "r") as devnull_in:
        os.dup2(devnull_in.fileno(), sys.stdin.fileno())

    with open("/dev/null", "a+") as devnull_out:
        os.dup2(devnull_out.fileno(), sys.stdout.fileno())

    with open("/dev/null", "a+") as devnull_err:
        os.dup2(devnull_err.fileno(), sys.stderr.fileno())


def _drop_privileges(
    user: str | None = None,
    group: str | None = None,
    umask_value: int | None = None,
):
    """
    Drop privileges to specified user/group and set umask.

    This must be called after binding to privileged ports (< 1024) but before
    starting application code to minimize security risk.

    Args:
        user: Username or UID to switch to
        group: Group name or GID to switch to
        umask_value: File creation mask (octal, e.g., 0o022)

    Raises:
        RuntimeError: If privilege dropping fails or not running as root
    """
    # Set umask first (doesn't require root)
    if umask_value is not None:
        os.umask(umask_value)
        print(
            f"[Worker {os.getpid()}] Set umask to {oct(umask_value)}",
            file=sys.stderr,
            flush=True,
        )

    # Privilege dropping requires root
    if user is None and group is None:
        return

    # Check if running as root
    if os.getuid() != 0:
        raise RuntimeError(
            "Cannot drop privileges: not running as root. "
            "user/group parameters require the server to be started as root."
        )

    # Get target UID and GID
    target_uid = None
    target_gid = None

    if group is not None:
        try:
            if isinstance(group, int) or group.isdigit():
                target_gid = int(group)
            else:
                target_gid = grp.getgrnam(group).gr_gid
        except KeyError:
            raise RuntimeError(f"Group '{group}' not found")

    if user is not None:
        try:
            if isinstance(user, int) or user.isdigit():
                target_uid = int(user)
                # Get user's default group if group not specified
                if target_gid is None:
                    target_gid = pwd.getpwuid(target_uid).pw_gid
            else:
                pw_record = pwd.getpwnam(user)
                target_uid = pw_record.pw_uid
                # Get user's default group if group not specified
                if target_gid is None:
                    target_gid = pw_record.pw_gid
        except KeyError:
            raise RuntimeError(f"User '{user}' not found")

    # Drop privileges (GID first, then UID - order matters!)
    try:
        if target_gid is not None:
            os.setgid(target_gid)
            print(
                f"[Worker {os.getpid()}] Switched to GID {target_gid}",
                file=sys.stderr,
                flush=True,
            )

        if target_uid is not None:
            os.setuid(target_uid)
            print(
                f"[Worker {os.getpid()}] Switched to UID {target_uid}",
                file=sys.stderr,
                flush=True,
            )
    except OSError as e:
        raise RuntimeError(f"Failed to drop privileges: {e}")

    # Verify we can't get root back
    if os.getuid() == 0 or os.geteuid() == 0:
        raise RuntimeError("Failed to drop root privileges")

    print(
        f"[Worker {os.getpid()}] Privileges dropped successfully "
        f"(UID={os.getuid()}, GID={os.getgid()})",
        file=sys.stderr,
        flush=True,
    )


def _worker_process(
    worker_id: int,
    socket_fd: int,
    apps: dict[str, Any],
    blocking_threads: int,
    last_activity: Value | None = None,  # type: ignore
    request_count: Value | None = None,  # type: ignore
    max_requests: int | None = None,
    max_requests_jitter: int | None = None,
    root_path: str = "",
    forwarded_allow_ips: list[str] | None = None,
    use_uvloop: bool = False,
    access_log: bool = True,
    user: str | None = None,
    group: str | None = None,
    umask_value: int | None = None,
    keepalive: int = 5,
    limit_concurrency: int | None = None,
):
    """
    Worker process function.

    Args:
        worker_id: Worker identifier
        socket_fd: Inherited socket file descriptor
        apps: Dictionary of mounted applications
        blocking_threads: Number of blocking threads per worker
        last_activity: Shared value for timeout monitoring
        request_count: Shared value for request counting
        max_requests: Maximum requests before worker restart
        max_requests_jitter: Random jitter for max_requests
        root_path: ASGI root_path for submounted applications
    """
    # Calculate request limit with jitter (prevents thundering herd)
    request_limit = None
    should_exit = False

    # Drop privileges early (after fork, before doing anything else)
    # This ensures all worker operations run with reduced privileges
    try:
        _drop_privileges(user=user, group=group, umask_value=umask_value)
    except RuntimeError as e:
        print(f"[Worker {worker_id}] ERROR: {e}", file=sys.stderr, flush=True)
        os._exit(1)

    if max_requests is not None:
        jitter = random.randint(0, max_requests_jitter or 0)
        request_limit = max_requests + jitter
        print(
            f"[Worker {worker_id}] Request limit: {request_limit} "
            f"(base={max_requests}, jitter={jitter})",
            file=sys.stderr,
            flush=True,
        )

    # Build apps dictionary - each handler uses its native type
    worker_apps = {}
    for prefix, app in apps.items():
        # All apps pass through as-is, no conversion needed
        worker_apps[prefix] = app

    # Create dictionary-based dispatcher for O(1) routing
    dispatcher = Dispatcher(
        worker_apps,
        root_path=root_path,
        forwarded_allow_ips=forwarded_allow_ips,
        use_uvloop=use_uvloop,
        access_log_enabled=access_log,
    )

    # Wrap dispatcher to track requests and activity
    def wrapped_handler(sender, method, path, headers, body, request_receiver=None):
        nonlocal should_exit

        # Mark worker as BUSY (handling request) for timeout monitoring
        if last_activity is not None:
            last_activity.value = time.time()  # type: ignore  # Set to current time = BUSY

        # Check and increment request counter ONCE per request
        if request_count is not None and request_limit is not None:
            with request_count.get_lock():  # type: ignore
                request_count.value += 1  # type: ignore
                current_count = request_count.value  # type: ignore

                # Check if we've reached the limit
                if current_count >= request_limit and not should_exit:
                    should_exit = True
                    print(
                        f"[Worker {worker_id}] Reached request limit "
                        f"({current_count}/{request_limit}). Will exit after this request...",
                        file=sys.stderr,
                        flush=True,
                    )

        # Handle the request normally
        try:
            dispatcher.handle_request(sender, method, path, headers, body, request_receiver)
        finally:
            # Mark worker as IDLE (request completed) - set to far future
            if last_activity is not None:
                last_activity.value = time.time() + 86400  # type: ignore  # Far future = IDLE

            # Exit after handling the limit-reaching request
            if should_exit:
                print(
                    f"[Worker {worker_id}] Exiting now (PID: {os.getpid()})",
                    file=sys.stderr,
                    flush=True,
                )
                os._exit(0)  # Force exit immediately

    # Create server with dedicated threads
    server = pyhtransport.DedicatedThreadServer(
        blocking_threads, keepalive=keepalive, limit_concurrency=limit_concurrency
    )

    print(
        f"[Worker {worker_id}] Started (PID: {os.getpid()}, threads: {blocking_threads})",
        file=sys.stderr,
        flush=True,
    )

    # Handle shutdown signals
    def handle_signal(signum, frame):
        print(
            f"[Worker {worker_id}] Shutting down (signal {signum})...",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        # Use fast path if no monitoring is needed
        if last_activity is None and request_count is None:
            # Fast path: No monitoring overhead - use dispatcher directly
            server.serve_fd(socket_fd, dispatcher.handle_request)
        else:
            # Slow path: Monitoring enabled - use wrapped_handler
            server.serve_fd(socket_fd, wrapped_handler)
    except Exception as e:
        print(f"[Worker {worker_id}] Error: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


def serve(
    apps: dict[str, Any],
    address: str = "0.0.0.0:8000",
    workers: int | None = None,
    blocking_threads: int = 2,
    tokio_threads: int | None = None,
    enable_worker_restart: bool = True,
    max_restarts_per_worker: int = 5,
    graceful_timeout: int = 30,
    pid_file: str | None = None,
    log_level: str | None = None,
    log_format: str | None = None,
    timeout: int = 30,
    keepalive: int = 5,
    max_requests: int | None = None,
    max_requests_jitter: int | None = None,
    backlog: int = 2048,
    limit_concurrency: int | None = None,
    limit_max_requests: int | None = None,
    timeout_keep_alive: int | None = None,
    root_path: str = "",
    use_uvloop: bool = False,
    app_dir: str | None = None,
    # Logging
    accesslog: str | None = None,
    errorlog: str | None = None,
    access_log: bool = True,
    use_colors: bool | None = None,
    # Proxy configuration
    forwarded_allow_ips: list[str] | None = None,
    # Process management
    user: str | None = None,
    group: str | None = None,
    umask: int | None = None,
    daemon: bool = False,
):
    """
    Server for WSGI/ASGI.

    This function provides a unified server with multiprocess architecture
    for optimal performance with dictionary-based O(1) routing.

    Args:
        apps: Dictionary mapping path prefixes to applications/handlers
              Example: {
                  '/': main_app,            # WSGI/ASGI app
                  '/api': fastapi_app,      # FastAPI app
                  '/admin': flask_app,      # Flask app
              }
        address: Address to bind to (default: "0.0.0.0:8000")
        workers: Number of worker processes (default: auto-detect based on CPUs/threads)
                 Set to 1 for single-process behavior (useful for debugging)
        blocking_threads: Number of blocking threads per worker (default: 2)
        tokio_threads: Number of Tokio I/O threads (default: 1, optimal for HTTP/1.1)
                       Set to 3 for HTTP/2-heavy workloads
                       Priority: tokio_threads parameter > TOKIO_WORKER_THREADS env var
                       > default (1)
        enable_worker_restart: Enable automatic worker restart on crash (default: True)
                               Disable for debugging to prevent masking crashes
        max_restarts_per_worker: Maximum number of restarts per worker (default: 5)
                                 Prevents infinite restart loops on persistent crashes
        graceful_timeout: Seconds to wait for workers to finish requests on shutdown (default: 30)
        pid_file: Path to PID file for process management (default: None)
                  Example: "/var/run/z.pid"
        log_level: Log level (DEBUG, INFO, WARNING, ERROR). Can be overridden by LOG_LEVEL env var.
        log_format: Log format ("text" or "json"). Can be overridden by LOG_FORMAT env var.

    Signals:
        SIGTERM/SIGINT: Graceful shutdown (wait for in-flight requests up to graceful_timeout)
        SIGHUP: Graceful reload (start new workers, gracefully shutdown old workers)

    Example:
        from z import serve
        from myapp import grpc_service, flask_app, fastapi_app

        # Development (single process, no auto-restart)
        serve(apps, workers=1, enable_worker_restart=False)

        # Production (auto-tuned multiprocess with auto-restart and PID file)
        serve(apps, pid_file="/var/run/myapp.pid")

        # Explicit configuration
        serve({
            '/': flask_app,
            '/api': fastapi_app,
        }, workers=4, blocking_threads=2, graceful_timeout=60, pid_file="/tmp/app.pid")
    """
    # Daemonize if requested (must be done before any other operations)
    if daemon:
        print("Daemonizing process...", file=sys.stderr, flush=True)
        _daemonize()
        # After daemonization, stdout/stderr are redirected to /dev/null
        # Only syslog or file logging will work from here

    # Parse address
    host, port = address.rsplit(":", 1)
    port = int(port)

    # PID file management
    if pid_file:
        # Check if PID file already exists
        if os.path.exists(pid_file):
            try:
                with open(pid_file, "r") as f:
                    old_pid = int(f.read().strip())
                # Check if process is still running
                try:
                    os.kill(old_pid, 0)  # Signal 0 checks if process exists
                    print(
                        f"ERROR: Server already running with PID {old_pid}",
                        file=sys.stderr,
                    )
                    print(f"PID file: {pid_file}", file=sys.stderr)
                    sys.exit(1)
                except OSError:
                    # Process doesn't exist, remove stale PID file
                    print(
                        f"Removing stale PID file (PID {old_pid} not running)",
                        file=sys.stderr,
                    )
                    os.remove(pid_file)
            except (ValueError, IOError) as e:
                print(f"Warning: Could not read PID file {pid_file}: {e}", file=sys.stderr)

        # Write current PID
        try:
            with open(pid_file, "w") as f:
                f.write(str(os.getpid()))
            print(f"PID file created: {pid_file} (PID: {os.getpid()})", file=sys.stderr)
        except IOError as e:
            print(f"ERROR: Could not write PID file {pid_file}: {e}", file=sys.stderr)
            sys.exit(1)

    # Set Tokio worker threads if specified
    if tokio_threads is not None:
        os.environ["TOKIO_WORKER_THREADS"] = str(tokio_threads)
        print(
            f"Setting TOKIO_WORKER_THREADS={tokio_threads}",
            file=sys.stderr,
            flush=True,
        )

    # Set log level if specified
    if log_level is not None:
        os.environ["LOG_LEVEL"] = log_level

    # Set log format if specified
    if log_format is not None:
        os.environ["LOG_FORMAT"] = log_format

    # Setup access logging
    setup_access_logging(
        enabled=access_log,
        use_colors=use_colors,
        log_file=accesslog,
    )

    # Setup error logging
    setup_error_logging(
        log_file=errorlog,
        log_level=log_level or "INFO",
    )

    # Auto-detect workers if not specified
    if workers is None:
        cpu_count = multiprocessing.cpu_count()
        workers = max(1, cpu_count // blocking_threads)
        print(
            f"Auto-detected {workers} workers for {cpu_count} CPUs "
            f"with {blocking_threads} threads per worker",
            file=sys.stderr,
            flush=True,
        )

    # Create and bind socket in parent process
    listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        listen_socket.bind((host, port))
    except OSError as e:
        print(f"Failed to bind to {host}:{port}: {e}", file=sys.stderr)
        raise

    listen_socket.listen(backlog)  # Use configurable backlog
    socket_fd = listen_socket.fileno()

    print(f"Parent bound to {host}:{port}, FD={socket_fd}", file=sys.stderr, flush=True)

    # Set multiprocessing start method
    try:
        multiprocessing.set_start_method("fork" if sys.platform != "win32" else "spawn", force=True)
    except RuntimeError:
        # Start method already set, ignore
        pass

    # Create shared memory for worker monitoring
    worker_last_activity: list[Value | None] = []  # type: ignore
    worker_request_counts: list[Value | None] = []  # type: ignore

    for i in range(workers):
        # Create last activity timestamp (for timeout monitoring)
        # Initialize to far future so idle workers don't timeout immediately
        last_activity = Value(c_double, time.time() + 86400) if timeout > 0 else None
        worker_last_activity.append(last_activity)

        # Create request counter (for max_requests)
        request_count = Value(c_int, 0) if max_requests is not None else None
        worker_request_counts.append(request_count)

    # Start worker processes
    worker_processes: list[multiprocessing.Process] = []
    for i in range(workers):
        p = multiprocessing.Process(
            target=_worker_process,
            args=(
                i,
                socket_fd,
                apps,
                blocking_threads,
                worker_last_activity[i],
                worker_request_counts[i],
                max_requests,
                max_requests_jitter,
                root_path,
                forwarded_allow_ips,
                use_uvloop,
                access_log,
                user,
                group,
                umask,
                keepalive,
                limit_concurrency,
            ),
        )
        p.start()
        worker_processes.append(p)
        print(f"[Main] Started worker {i} with PID {p.pid}", file=sys.stderr, flush=True)

    # Print server info
    print("\n" + "=" * 60, file=sys.stderr)
    print("Unified Multiprocess Server", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"Address: {host}:{port}", file=sys.stderr)
    print(f"Workers: {workers}", file=sys.stderr)
    print(f"Threads per worker: {blocking_threads}", file=sys.stderr)
    print(f"Total threads: {workers * blocking_threads}", file=sys.stderr)
    print("RPC handlers: Automatically optimized per handler type", file=sys.stderr)
    if enable_worker_restart:
        print(
            f"Worker auto-restart: Enabled (max {max_restarts_per_worker} restarts/worker)",
            file=sys.stderr,
        )
    else:
        print("Worker auto-restart: Disabled", file=sys.stderr)
    if timeout > 0:
        print(f"Worker timeout: {timeout}s", file=sys.stderr)
    if max_requests is not None:
        jitter_info = f" (jitter: {max_requests_jitter})" if max_requests_jitter else ""
        print(f"Max requests per worker: {max_requests}{jitter_info}", file=sys.stderr)
    print("=" * 60 + "\n", file=sys.stderr, flush=True)

    # Track restart counts for each worker slot (not PID, but worker index)
    restart_counts = [0] * workers

    # Graceful reload flag
    reload_requested = False
    shutdown_requested = False

    # Signal handlers
    def handle_reload(signum, frame):
        """Handle SIGHUP for graceful reload"""
        nonlocal reload_requested
        reload_requested = True
        print(
            "\n[Main] Received SIGHUP - Graceful reload requested",
            file=sys.stderr,
            flush=True,
        )

    def handle_shutdown(signum, frame):
        """Handle SIGTERM/SIGINT for graceful shutdown"""
        nonlocal shutdown_requested
        shutdown_requested = True
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        print(
            f"\n[Main] Received {sig_name} - Graceful shutdown requested",
            file=sys.stderr,
            flush=True,
        )

    # Register signal handlers
    signal.signal(signal.SIGHUP, handle_reload)
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Worker monitoring and auto-restart loop
    def monitor_workers():
        """Monitor workers and restart crashed ones. Zero overhead for workers."""
        nonlocal reload_requested, shutdown_requested

        while not shutdown_requested:
            time.sleep(1)  # Check every second (minimal overhead)

            # Check for timed-out workers (if timeout monitoring enabled)
            if timeout > 0:
                current_time = time.time()
                for i, last_activity in enumerate(worker_last_activity):
                    if last_activity is not None and worker_processes[i].is_alive():
                        # Only check timeout if worker has handled at least one request
                        # (prevents idle workers from timing out)
                        # Skip if request count is 0 OR if it's far future (never updated)
                        if (
                            worker_request_counts[i] is not None
                            and worker_request_counts[i].value == 0  # type: ignore
                        ):
                            continue  # Skip workers that haven't handled any requests yet

                        time_since_activity = current_time - last_activity.value  # type: ignore
                        if time_since_activity < 0:
                            continue  # Skip if timestamp is in future (not yet updated)
                        if time_since_activity > timeout:
                            print(
                                f"[Main] Worker {i} (PID {worker_processes[i].pid}) timed out "
                                f"({time_since_activity:.1f}s > {timeout}s). Killing...",
                                file=sys.stderr,
                                flush=True,
                            )
                            worker_processes[i].kill()
                            worker_processes[i].join()

            # Handle graceful reload
            if reload_requested:
                reload_requested = False
                print("[Main] Starting graceful reload...", file=sys.stderr, flush=True)

                # Create new shared memory for new workers
                new_last_activity = []
                new_request_counts = []
                for i in range(workers):
                    # Initialize to far future so idle workers don't timeout immediately
                    last_activity = Value(c_double, time.time() + 86400) if timeout > 0 else None
                    new_last_activity.append(last_activity)
                    request_count = Value(c_int, 0) if max_requests is not None else None
                    new_request_counts.append(request_count)

                # Start new workers
                new_workers = []
                for i in range(workers):
                    p = multiprocessing.Process(
                        target=_worker_process,
                        args=(
                            i,
                            socket_fd,
                            apps,
                            blocking_threads,
                            new_last_activity[i],
                            new_request_counts[i],
                            max_requests,
                            max_requests_jitter,
                            root_path,
                            forwarded_allow_ips,
                            use_uvloop,
                            access_log,
                            user,
                            group,
                            umask,
                            keepalive,
                            limit_concurrency,
                        ),
                    )
                    p.start()
                    new_workers.append(p)
                    print(
                        f"[Main] Started new worker {i} with PID {p.pid}",
                        file=sys.stderr,
                        flush=True,
                    )

                # Gracefully shutdown old workers
                print(
                    f"[Main] Shutting down old workers (graceful_timeout={graceful_timeout}s)...",
                    file=sys.stderr,
                    flush=True,
                )
                for i, p in enumerate(worker_processes):
                    p.terminate()  # Send SIGTERM

                # Wait for old workers to finish
                for i, p in enumerate(worker_processes):
                    p.join(timeout=graceful_timeout)
                    if p.is_alive():
                        print(
                            f"[Main] Old worker {i} (PID {p.pid}) "
                            f"did not exit gracefully, killing...",
                            file=sys.stderr,
                            flush=True,
                        )
                        p.kill()
                        p.join()
                    else:
                        print(
                            f"[Main] Old worker {i} (PID {p.pid}) exited gracefully",
                            file=sys.stderr,
                            flush=True,
                        )

                # Replace with new workers
                worker_processes[:] = new_workers
                worker_last_activity[:] = new_last_activity
                worker_request_counts[:] = new_request_counts
                restart_counts[:] = [0] * workers  # Reset restart counts
                print("[Main] Graceful reload complete", file=sys.stderr, flush=True)
                continue

            # Check for crashed workers
            for i, process in enumerate(worker_processes):
                if not process.is_alive():
                    exit_code = process.exitcode

                    # Only restart on abnormal exit (non-zero exit code)
                    # Exit code 0 means normal termination (e.g., SIGTERM, graceful shutdown)
                    if exit_code != 0:
                        if enable_worker_restart and restart_counts[i] < max_restarts_per_worker:
                            # Worker crashed, restart it
                            restart_counts[i] += 1
                            print(
                                f"[Main] Worker {i} (PID {process.pid}) "
                                f"crashed with exit code {exit_code}. "
                                f"Restarting ({restart_counts[i]}/{max_restarts_per_worker})...",
                                file=sys.stderr,
                                flush=True,
                            )
                        else:
                            # Max restarts reached or restart disabled
                            print(
                                f"[Main] Worker {i} (PID {process.pid}) "
                                f"crashed with exit code {exit_code}. "
                                f"Not restarting "
                                f"(restarts: {restart_counts[i]}/{max_restarts_per_worker}).",
                                file=sys.stderr,
                                flush=True,
                            )
                            continue
                    else:
                        # Exit code 0 = normal termination (logged but not restarted)
                        print(
                            f"[Main] Worker {i} (PID {process.pid}) exited normally (exit code 0).",
                            file=sys.stderr,
                            flush=True,
                        )
                        continue

                    # Create new shared memory for restarted worker
                    # Initialize to far future so idle workers don't timeout immediately
                    new_last_activity = (
                        Value(c_double, time.time() + 86400) if timeout > 0 else None
                    )
                    new_request_count = Value(c_int, 0) if max_requests is not None else None
                    worker_last_activity[i] = new_last_activity
                    worker_request_counts[i] = new_request_count

                    # Start new worker in the same slot
                    new_process = multiprocessing.Process(
                        target=_worker_process,
                        args=(
                            i,
                            socket_fd,
                            apps,
                            blocking_threads,
                            new_last_activity,
                            new_request_count,
                            max_requests,
                            max_requests_jitter,
                            root_path,
                            forwarded_allow_ips,
                            use_uvloop,
                            access_log,
                            user,
                            group,
                            umask,
                            keepalive,
                            limit_concurrency,
                        ),
                    )
                    new_process.start()
                    worker_processes[i] = new_process

                    print(
                        f"[Main] Worker {i} restarted with new PID {new_process.pid}",
                        file=sys.stderr,
                        flush=True,
                    )

    # Graceful shutdown helper
    def graceful_shutdown():
        """Gracefully shutdown all workers"""
        print(
            f"[Main] Shutting down workers (graceful_timeout={graceful_timeout}s)...",
            file=sys.stderr,
            flush=True,
        )

        # Send SIGTERM to all workers
        for i, p in enumerate(worker_processes):
            if p.is_alive():
                p.terminate()

        # Wait for workers to finish
        for i, p in enumerate(worker_processes):
            p.join(timeout=graceful_timeout)
            if p.is_alive():
                print(
                    f"[Main] Worker {i} (PID {p.pid}) did not exit gracefully, killing...",
                    file=sys.stderr,
                    flush=True,
                )
                p.kill()
                p.join()
            else:
                print(
                    f"[Main] Worker {i} (PID {p.pid}) exited gracefully",
                    file=sys.stderr,
                    flush=True,
                )

        print("[Main] Shutdown complete", file=sys.stderr, flush=True)

    # Wait for workers with monitoring (always use monitor loop for signal handling)
    try:
        monitor_workers()
    except KeyboardInterrupt:
        shutdown_requested = True
        print("\n[Main] Received KeyboardInterrupt", file=sys.stderr, flush=True)
    finally:
        # Graceful shutdown
        if not all(not p.is_alive() for p in worker_processes):
            graceful_shutdown()

        # Cleanup
        listen_socket.close()

        # Remove PID file
        if pid_file and os.path.exists(pid_file):
            try:
                os.remove(pid_file)
                print(f"PID file removed: {pid_file}", file=sys.stderr)
            except IOError as e:
                print(
                    f"Warning: Could not remove PID file {pid_file}: {e}",
                    file=sys.stderr,
                )


def serve_fd(
    apps: dict[str, Any],
    fd: int,
    blocking_threads: int = 2,
    tokio_threads: int | None = None,
    log_level: str | None = None,
    log_format: str | None = None,
    keepalive: int = 5,
    limit_concurrency: int | None = None,
):
    """
    Serve applications using a pre-opened file descriptor (for systemd socket activation).

    Args:
        apps: Dictionary mapping path prefixes to applications
        fd: File descriptor number (typically 3 from systemd)
        blocking_threads: Number of blocking threads per worker (default: 2)
        tokio_threads: Number of Tokio I/O threads (default: 1)
        log_level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_format: Log format ("text" or "json")

    Example:
        # systemd socket activation
        serve_fd({'/': app}, fd=3, blocking_threads=2)
    """
    # Set Tokio worker threads if specified
    if tokio_threads is not None:
        os.environ["TOKIO_WORKER_THREADS"] = str(tokio_threads)

    # Set log level if specified
    if log_level is not None:
        os.environ["LOG_LEVEL"] = log_level

    # Set log format if specified
    if log_format is not None:
        os.environ["LOG_FORMAT"] = log_format

    # Build apps dictionary
    worker_apps = {}
    for prefix, app in apps.items():
        worker_apps[prefix] = app

    # Create dispatcher
    dispatcher = Dispatcher(worker_apps)

    # Create server with dedicated threads
    server = pyhtransport.DedicatedThreadServer(
        blocking_threads, keepalive=keepalive, limit_concurrency=limit_concurrency
    )

    print(
        f"Server starting on FD {fd} with {blocking_threads} blocking threads",
        file=sys.stderr,
        flush=True,
    )

    # Serve using file descriptor
    server.serve_fd(fd, dispatcher.handle_request)


def serve_uds(
    apps: dict[str, Any],
    socket_path: str,
    blocking_threads: int = 2,
    tokio_threads: int | None = None,
    log_level: str | None = None,
    log_format: str | None = None,
    keepalive: int = 5,
    limit_concurrency: int | None = None,
):
    """
    Serve applications using a Unix domain socket.

    Args:
        apps: Dictionary mapping path prefixes to applications
        socket_path: Unix socket file path (e.g., "/tmp/z.sock")
        blocking_threads: Number of blocking threads per worker (default: 2)
        tokio_threads: Number of Tokio I/O threads (default: 1)
        log_level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_format: Log format ("text" or "json")

    Example:
        # Unix domain socket
        serve_uds({'/': app}, socket_path="/tmp/z.sock", blocking_threads=2)
    """
    # Set Tokio worker threads if specified
    if tokio_threads is not None:
        os.environ["TOKIO_WORKER_THREADS"] = str(tokio_threads)

    # Set log level if specified
    if log_level is not None:
        os.environ["LOG_LEVEL"] = log_level

    # Set log format if specified
    if log_format is not None:
        os.environ["LOG_FORMAT"] = log_format

    # Build apps dictionary
    worker_apps = {}
    for prefix, app in apps.items():
        worker_apps[prefix] = app

    # Create dispatcher
    dispatcher = Dispatcher(worker_apps)

    # Create server with dedicated threads
    server = pyhtransport.DedicatedThreadServer(
        blocking_threads, keepalive=keepalive, limit_concurrency=limit_concurrency
    )

    print(
        f"Server starting on Unix socket {socket_path} with {blocking_threads} blocking threads",
        file=sys.stderr,
        flush=True,
    )

    # Serve using Unix domain socket
    server.serve_uds(socket_path, dispatcher.handle_request)
