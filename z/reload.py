"""
Auto-reload functionality for development mode.

This module provides file watching and automatic server restart
when source files change, similar to uvicorn's --reload functionality.
"""

import logging
import signal
import threading
from multiprocessing import Process
from pathlib import Path
from typing import Callable

try:
    from watchfiles import watch
except ImportError:
    watch = None

logger = logging.getLogger("z.reload")


class Reloader:
    """
    File watcher that monitors source code changes and triggers server restarts.

    Uses watchfiles for efficient file system monitoring.
    """

    def __init__(
        self,
        target: Callable,
        args: tuple = (),
        kwargs: dict | None = None,
        reload_dirs: list[str] | None = None,
        reload_includes: list[str] | None = None,
        reload_excludes: list[str] | None = None,
        reload_delay: float = 0.25,
    ):
        """
        Initialize the reloader.

        Args:
            target: The function to run (server startup function)
            args: Positional arguments for target
            kwargs: Keyword arguments for target
            reload_dirs: List of directories to watch (default: current directory)
            reload_includes: List of file patterns to include (default: *.py)
            reload_excludes: List of file patterns to exclude
            reload_delay: Time to wait before reloading after detecting changes (seconds)
        """
        if watch is None:
            raise RuntimeError(
                "watchfiles is not installed. Install it with: pip install watchfiles"
            )

        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.reload_delay = reload_delay
        self.should_exit = threading.Event()
        self.process: Process | None = None

        # Configure watch directories
        if reload_dirs:
            self.watch_dirs = [Path(d).resolve() for d in reload_dirs]
        else:
            # Default: watch current directory
            self.watch_dirs = [Path.cwd()]

        # Configure file patterns
        self.reload_includes = reload_includes or ["*.py"]
        self.reload_excludes = reload_excludes or [
            ".git/*",
            ".venv/*",
            "venv/*",
            "__pycache__/*",
            "*.pyc",
            ".pytest_cache/*",
            ".mypy_cache/*",
            ".ruff_cache/*",
            "build/*",
            "dist/*",
            "*.egg-info/*",
        ]

        logger.info(
            f"Watching for file changes in: {', '.join(str(d) for d in self.watch_dirs)}"
        )

    def startup(self) -> None:
        """Start the server process."""
        logger.info("Starting server process...")
        self.process = Process(target=self.target, args=self.args, kwargs=self.kwargs)
        self.process.start()

    def shutdown(self) -> None:
        """Stop the server process."""
        if self.process and self.process.is_alive():
            logger.info("Stopping server process...")
            self.process.terminate()
            self.process.join(timeout=5)
            if self.process.is_alive():
                logger.warning("Forcefully killing server process...")
                self.process.kill()
                self.process.join()

    def restart(self) -> None:
        """Restart the server process."""
        logger.info("Detected file change, restarting server...")
        self.shutdown()
        self.startup()

    def should_watch_file(self, path: Path) -> bool:
        """
        Check if a file should be watched based on include/exclude patterns.

        Args:
            path: Path to check

        Returns:
            True if file should be watched, False otherwise
        """
        path_str = str(path)

        # Check excludes first
        for pattern in self.reload_excludes:
            if self._match_pattern(path_str, pattern):
                return False

        # Check includes
        for pattern in self.reload_includes:
            if self._match_pattern(path_str, pattern):
                return True

        return False

    @staticmethod
    def _match_pattern(path: str, pattern: str) -> bool:
        """
        Simple pattern matching for file paths.

        Supports:
        - Exact matches
        - Wildcard * (e.g., *.py)
        - Directory patterns (e.g., .git/*)
        """
        if "*" not in pattern:
            return pattern in path

        # Simple wildcard matching
        parts = pattern.split("*")
        pos = 0
        for i, part in enumerate(parts):
            if not part:
                continue
            idx = path.find(part, pos)
            if idx == -1:
                return False
            if i == 0 and idx != 0:
                return False
            pos = idx + len(part)

        return True

    def run(self) -> None:
        """
        Run the reloader loop.

        Starts the server and watches for file changes.
        Restarts the server when changes are detected.
        """

        # Set up signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            self.should_exit.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Start the server
        self.startup()

        try:
            # Watch for file changes
            for changes in watch(*self.watch_dirs, stop_event=self.should_exit):  # type: ignore
                if self.should_exit.is_set():
                    break

                # Filter changes based on include/exclude patterns
                relevant_changes = []
                for change_type, changed_path in changes:
                    path = Path(changed_path)
                    if self.should_watch_file(path):
                        relevant_changes.append((change_type, changed_path))
                        logger.debug(f"File changed: {changed_path}")

                # Restart if any relevant files changed
                if relevant_changes:
                    # Wait for reload_delay before restarting
                    if self.reload_delay > 0:
                        logger.info(f"Waiting {self.reload_delay}s before reloading...")
                        self.should_exit.wait(timeout=self.reload_delay)
                        if self.should_exit.is_set():
                            break
                    self.restart()

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.shutdown()
            logger.info("Reloader stopped")


def run_with_reload(
    target: Callable,
    args: tuple = (),
    kwargs: dict | None = None,
    reload_dirs: list[str] | None = None,
    reload_includes: list[str] | None = None,
    reload_excludes: list[str] | None = None,
    reload_delay: float = 0.25,
) -> None:
    """
    Run a function with auto-reload on file changes.

    This is the main entry point for enabling reload functionality.

    Args:
        target: The function to run (server startup function)
        args: Positional arguments for target
        kwargs: Keyword arguments for target
        reload_dirs: List of directories to watch
        reload_includes: List of file patterns to include
        reload_excludes: List of file patterns to exclude
        reload_delay: Time to wait before reloading after detecting changes (seconds)

    Example:
        >>> def start_server(host, port):
        ...     serve({"/": app}, address=f"{host}:{port}")
        >>> run_with_reload(start_server, args=("0.0.0.0", 8000))
    """
    reloader = Reloader(
        target=target,
        args=args,
        kwargs=kwargs,
        reload_dirs=reload_dirs,
        reload_includes=reload_includes,
        reload_excludes=reload_excludes,
        reload_delay=reload_delay,
    )
    reloader.run()
