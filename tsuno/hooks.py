"""
Gunicorn-compatible server hooks system.

Provides lifecycle hooks at various server and worker stages,
enabling users to customize server behavior without modifying code.

Example usage in configuration file (z.conf.py):

    def when_ready(server):
        print(f"Server ready on {server['address']}")

    def pre_request(worker, req):
        print(f"Processing {req['method']} {req['path']}")

For complete examples, see examples/z_with_hooks.conf.py
"""

import sys
from typing import Any, Callable


class ServerHooks:
    """
    Container for Gunicorn-compatible server hooks.

    All hooks are optional callable functions loaded from config files.
    Hooks follow Gunicorn's signature conventions for maximum compatibility.

    Hook Categories:
        - Master Process: on_starting, on_reload, when_ready, on_exit
        - Worker Lifecycle: pre_fork, post_fork, post_worker_init, child_exit, worker_exit
        - Signals: worker_int, worker_abort
        - Workers Changed: nworkers_changed
        - Requests: pre_request, post_request
        - Advanced: pre_exec, ssl_context
    """

    def __init__(self, config: dict[str, Any]):
        """
        Initialize hooks from configuration dictionary.

        Args:
            config: Configuration dictionary containing hook functions
        """
        # Master process hooks
        self.on_starting: Callable | None = config.get("on_starting")
        self.on_reload: Callable | None = config.get("on_reload")
        self.when_ready: Callable | None = config.get("when_ready")
        self.on_exit: Callable | None = config.get("on_exit")

        # Worker lifecycle hooks
        self.pre_fork: Callable | None = config.get("pre_fork")
        self.post_fork: Callable | None = config.get("post_fork")
        self.post_worker_init: Callable | None = config.get("post_worker_init")
        self.child_exit: Callable | None = config.get("child_exit")
        self.worker_exit: Callable | None = config.get("worker_exit")

        # Signal hooks
        self.worker_int: Callable | None = config.get("worker_int")
        self.worker_abort: Callable | None = config.get("worker_abort")

        # Workers changed hook
        self.nworkers_changed: Callable | None = config.get("nworkers_changed")

        # Request hooks
        self.pre_request: Callable | None = config.get("pre_request")
        self.post_request: Callable | None = config.get("post_request")

        # Advanced hooks
        self.pre_exec: Callable | None = config.get("pre_exec")
        self.ssl_context: Callable | None = config.get("ssl_context")

    def safe_call(self, hook_name: str, *args, **kwargs) -> None:
        """
        Safely call a hook function with error handling.

        Hook errors should not crash the server - they are logged and ignored.
        This ensures that user-defined hooks cannot break server operation.

        Args:
            hook_name: Name of the hook to call (e.g., "when_ready")
            *args: Positional arguments to pass to the hook
            **kwargs: Keyword arguments to pass to the hook

        Example:
            hooks.safe_call("when_ready", server_info)
            hooks.safe_call("pre_request", worker_info, request_info)
        """
        hook = getattr(self, hook_name, None)
        if hook and callable(hook):
            try:
                hook(*args, **kwargs)
            except Exception as e:
                # Log error but don't crash the server
                print(
                    f"[Hooks] Error in {hook_name}: {e}",
                    file=sys.stderr,
                    flush=True,
                )

    def has_hook(self, hook_name: str) -> bool:
        """
        Check if a hook is defined.

        Args:
            hook_name: Name of the hook to check

        Returns:
            True if the hook is defined and callable, False otherwise
        """
        hook = getattr(self, hook_name, None)
        return hook is not None and callable(hook)


# Hook signatures documentation (for reference)
HOOK_SIGNATURES = {
    # Master process hooks
    "on_starting": "def on_starting(server)",
    "on_reload": "def on_reload(server)",
    "when_ready": "def when_ready(server)",
    "on_exit": "def on_exit(server)",
    # Worker lifecycle hooks
    "pre_fork": "def pre_fork(server, worker)",
    "post_fork": "def post_fork(server, worker)",
    "post_worker_init": "def post_worker_init(worker)",
    "child_exit": "def child_exit(server, worker)",
    "worker_exit": "def worker_exit(server, worker)",
    # Signal hooks
    "worker_int": "def worker_int(worker)",
    "worker_abort": "def worker_abort(worker)",
    # Workers changed
    "nworkers_changed": "def nworkers_changed(server, new_value, old_value)",
    # Request hooks
    "pre_request": "def pre_request(worker, req)",
    "post_request": "def post_request(worker, req, environ, resp)",
    # Advanced hooks
    "pre_exec": "def pre_exec(server)",
    "ssl_context": "def ssl_context(config, default_ssl_context_factory)",
}
