"""
Lightweight unified dispatcher for WSGI and ASGI applications.

This dispatcher provides simple prefix-based routing for web applications.
"""

import inspect
import time
from typing import Any

from .access_log import log_request
from .asgi_adapter import ASGIAdapter
from .wsgi_adapter import WSGIAdapter


class ResponseSenderWrapper:
    """Wrapper for ResponseSender to intercept status codes for access logging."""

    def __init__(self, sender):
        self._sender = sender
        self.status_code = 500  # Default status

    def send_response(self, status, headers, body, trailers=None):
        """Intercept status code and forward to actual sender"""
        self.status_code = status
        return self._sender.send_response(status, headers, body, trailers)

    def send_start(self, status, headers):
        """Intercept status code for streaming responses"""
        self.status_code = status
        return self._sender.send_start(status, headers)

    def send_chunk(self, data, more_body=True):
        """Forward chunk sending to actual sender"""
        return self._sender.send_chunk(data, more_body)

    def send_trailers(self, trailers):
        """Forward trailer sending to actual sender"""
        return self._sender.send_trailers(trailers)

    def is_streaming(self):
        """Check if sender supports streaming"""
        return hasattr(self._sender, "is_streaming") and self._sender.is_streaming()

    def __getattr__(self, name):
        """Forward all other attributes to the actual sender"""
        return getattr(self._sender, name)


class Dispatcher:
    """
    Unified dispatcher with prefix-based routing for WSGI/ASGI applications.

    Key features:
    - Prefix-based path matching
    - Automatic WSGI/ASGI detection
    - Pre-cached adapter instances
    """

    def __init__(
        self,
        mounts: dict[str, Any],
        default_app: Any = None,
        root_path: str = "",
        forwarded_allow_ips: list[str] | None = None,
        use_uvloop: bool = True,
        access_log_enabled: bool = True,
    ):
        """
        Initialize dispatcher with mounted applications.

        Args:
            mounts: Dictionary mapping path prefixes to applications
                   Example: {'/': flask_app, '/api': fastapi_app}
            default_app: Optional default application for unmatched paths
            root_path: ASGI root_path for submounted applications
            forwarded_allow_ips: List of trusted proxy IPs for X-Forwarded-For/X-Real-IP headers
            use_uvloop: Enable uvloop for ASGI applications
            access_log_enabled: Enable access logging (default: True)
        """
        # List for WSGI/ASGI prefix matching
        self.prefix_apps = []  # [(prefix, app, adapter)]
        self.default_app = default_app
        self.default_adapter = None
        self.root_path = root_path
        self.forwarded_allow_ips = set(forwarded_allow_ips or [])
        self.use_uvloop = use_uvloop
        self.access_log_enabled = access_log_enabled

        # Process mounted apps
        for prefix, app in mounts.items():
            # Normalize prefix
            prefix = prefix.rstrip("/")
            if not prefix.startswith("/"):
                prefix = "/" + prefix

            # Create adapter and store
            adapter = self._create_adapter(app)
            self.prefix_apps.append((prefix, app, adapter))

        # Sort prefix apps by length (longest first) for proper matching
        self.prefix_apps.sort(key=lambda x: len(x[0]), reverse=True)

        # Create adapter for default app if provided
        if self.default_app:
            self.default_adapter = self._create_adapter(self.default_app)

    def _create_adapter(self, app: Any) -> WSGIAdapter | ASGIAdapter:
        """
        Create appropriate adapter for app.

        Automatically detects WSGI vs ASGI based on app introspection.

        Args:
            app: WSGI or ASGI application

        Returns:
            WSGIAdapter or ASGIAdapter instance
        """
        if hasattr(app, "routes"):  # FastAPI/Starlette
            return ASGIAdapter(app, root_path=self.root_path, use_uvloop=self.use_uvloop)
        elif hasattr(app, "wsgi_app"):  # Flask
            return WSGIAdapter(app)
        else:
            # Check if it's async
            if hasattr(app, "__call__"):
                # Check both the app itself and its __call__ method
                if (
                    inspect.iscoroutinefunction(app)
                    or inspect.isasyncgenfunction(app)
                    or inspect.iscoroutinefunction(app.__call__)
                ):
                    return ASGIAdapter(app, root_path=self.root_path, use_uvloop=self.use_uvloop)
                else:
                    return WSGIAdapter(app)
            else:
                # Default to ASGI
                return ASGIAdapter(app, root_path=self.root_path, use_uvloop=self.use_uvloop)

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
        Route request to appropriate application based on path prefix.

        Args:
            sender: ResponseSender object from Rust to send response
            method: HTTP method
            path: Request path
            headers: Request headers as list of tuples
            body: Request body
        """
        # Use wrapper and time measurement only when access log is enabled
        if self.access_log_enabled:
            # Extract client address from headers (X-Forwarded-For or X-Real-IP)
            client_addr = "-"

            # If forwarded_allow_ips is configured, trust proxy headers
            trust_proxy = len(self.forwarded_allow_ips) > 0
            if trust_proxy:
                for name, value in headers:
                    if name.lower() == "x-forwarded-for":
                        # Take the first IP in the chain
                        client_addr = value.split(",")[0].strip()
                        break
                    elif name.lower() == "x-real-ip":
                        client_addr = value
                        break

            # Determine HTTP version from headers
            http_version = "1.1"  # Default
            for name, value in headers:
                if name.lower() == ":authority":
                    # HTTP/2 pseudo-header
                    http_version = "2.0"
                    break

            # Track start time for duration
            start_time = time.time()

            # Wrap sender to capture status code for access logging
            sender = ResponseSenderWrapper(sender)

        try:
            # Try prefix matching for WSGI/ASGI apps
            for prefix, app, adapter in self.prefix_apps:
                if prefix == "/":
                    # Root prefix matches everything
                    if path == "/" or path.startswith("/"):
                        adjusted_path = path
                        adapter.handle_request(
                            sender,
                            method,
                            adjusted_path,
                            headers,
                            body,
                            request_receiver,
                        )
                        return
                elif path.startswith(prefix + "/") or path == prefix:
                    # Adjust path by removing prefix
                    adjusted_path = path[len(prefix) :] or "/"
                    adapter.handle_request(
                        sender,
                        method,
                        adjusted_path,
                        headers,
                        body,
                        request_receiver,
                    )
                    return

            # Try default app
            if self.default_app and self.default_adapter:
                self.default_adapter.handle_request(sender, method, path, headers, body, request_receiver)
            else:
                # No app found - send 404
                sender.send_response(404, [("Content-Type", "text/plain")], b"404 Not Found", None)
        finally:
            # Log access only when access log is enabled
            if self.access_log_enabled and start_time is not None:  # type: ignore
                duration = time.time() - start_time  # type: ignore
                log_request(
                    client_addr=client_addr,  # type: ignore
                    method=method,
                    path=path,
                    http_version=http_version,  # type: ignore
                    status_code=sender.status_code,  # type: ignore
                    duration=duration,
                )
