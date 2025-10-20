"""
ASGI adapter for serving ASGI applications with the Tsuno server.

This module provides compatibility with ASGI applications
(FastAPI, Starlette, Quart, connect-python, etc.).

This adapter uses a dedicated event loop worker architecture,
allowing concurrent request processing without blocking the event loop.
"""

import sys
from typing import Callable

from .asgi_event_loop_worker import ASGIEventLoopWorker


class ASGIAdapter:
    """
    ASGI adapter with dedicated event loop.

    This adapter uses ASGIEventLoopWorker to run requests concurrently
    in a dedicated event loop thread.
    """

    def __init__(self, asgi_app: Callable, root_path: str = "", use_uvloop: bool = False):
        """
        Initialize the ASGI adapter.

        Args:
            asgi_app: An ASGI application callable
            root_path: ASGI root_path for submounted applications
            use_uvloop: Enable uvloop for application-level I/O acceleration
        """
        self.asgi_app = asgi_app
        self.root_path = root_path
        self.use_uvloop = use_uvloop

        # Create dedicated event loop worker
        self.worker = ASGIEventLoopWorker(asgi_app, root_path=root_path, use_uvloop=use_uvloop)

        print(
            "[ASGI] Initialized with dedicated event loop worker",
            file=sys.stderr,
        )

    def handle_request(
        self,
        sender,  # ResponseSender from Rust
        method: str,
        path: str,
        headers: list[tuple[str, str]],
        body: bytes,
        request_receiver=None,  # Optional RequestReceiver for full-duplex streaming
    ) -> None:
        """
        Handle an HTTP request by submitting it to the event loop worker.

        This method returns immediately (non-blocking), allowing concurrent
        request processing in the dedicated event loop thread.

        Args:
            sender: ResponseSender object from Rust to send the response
            method: HTTP method
            path: Request path
            headers: Request headers
            body: Request body
            request_receiver: Optional RequestReceiver for streaming request body (full-duplex)
        """
        # Submit request to event loop worker (non-blocking)
        self.worker.handle_request_non_blocking(
            sender, method, path, headers, body, request_receiver
        )

        # Return immediately - request will be processed asynchronously

    def shutdown(self) -> None:
        """
        Shutdown the ASGI adapter.
        This should be called when the server is shutting down.
        """
        self.worker.shutdown()
