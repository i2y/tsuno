"""
Dedicated Event Loop Worker for ASGI applications.

This module provides a high-performance ASGI execution model by running
a dedicated AsyncIO event loop in a separate thread.
"""

import asyncio
import sys
import threading
import time
from typing import Any, Callable
from urllib.parse import unquote, urlsplit


class ASGIEventLoopWorker:
    """
    Dedicated event loop worker for ASGI applications.

    This worker maintains a constantly running event loop in a dedicated thread,
    allowing true concurrent request processing without blocking.

    Architecture:
    - Main thread: Receives requests from Rust layer
    - Event loop thread: Runs AsyncIO loop continuously
    - Requests are scheduled as tasks without blocking
    """

    def __init__(self, asgi_app: Callable, root_path: str = "", use_uvloop: bool = False):
        """
        Initialize the event loop worker.

        Args:
            asgi_app: ASGI application callable
            root_path: ASGI root_path for submounted applications
            use_uvloop: Enable uvloop for application-level I/O acceleration
        """
        self.asgi_app = asgi_app
        self.root_path = root_path
        self.use_uvloop = use_uvloop
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None
        self.lifespan_started = False
        self.lifespan_shutdown = False
        self.lifespan_task: asyncio.Task | None = None
        self.lifespan_startup_complete: asyncio.Event | None = None
        self.lifespan_shutdown_complete: asyncio.Event | None = None

        # Start event loop in dedicated thread
        self._start_event_loop()

        # Run lifespan startup
        self._run_lifespan_startup()

    def _start_event_loop(self):
        """Start AsyncIO event loop in dedicated thread."""

        def run_loop():
            # Install uvloop if requested
            if self.use_uvloop:
                try:
                    import uvloop

                    uvloop.install()
                except ImportError:
                    import warnings

                    warnings.warn(
                        "uvloop requested but not installed. "
                        "Install with: pip install tsuno[uvloop]\n"
                        "Falling back to standard asyncio.",
                        RuntimeWarning,
                        stacklevel=2,
                    )

            # Create event loop (uvloop or standard asyncio)
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            # Run event loop forever (non-blocking architecture)
            self.loop.run_forever()

        self.thread = threading.Thread(target=run_loop, daemon=True, name="asgi-event-loop")
        self.thread.start()

        # Wait for loop to be ready (with timeout)
        timeout = time.time() + 5.0
        while self.loop is None:
            if time.time() > timeout:
                raise RuntimeError("Event loop failed to start within 5 seconds")
            time.sleep(0.001)

    def handle_request_non_blocking(
        self,
        sender,  # ResponseSender from Rust
        method: str,
        path: str,
        headers: list[tuple[str, str]],
        body: bytes,
        request_receiver=None,  # Optional RequestReceiver for full-duplex streaming
    ) -> None:
        """
        Submit request to event loop for processing (non-blocking).

        This method returns immediately, allowing the caller to process
        other requests concurrently.

        Args:
            sender: ResponseSender object from Rust
            method: HTTP method
            path: Request path
            headers: Request headers
            body: Request body
            request_receiver: Optional RequestReceiver for streaming request body (full-duplex)
        """
        # Create coroutine and schedule it in event loop
        coro = self._handle_request_async(sender, method, path, headers, body, request_receiver)

        # Schedule task
        self.loop.call_soon_threadsafe(self._schedule_task, coro)  # type: ignore

        # Return immediately - request will be processed asynchronously

    def _schedule_task(self, coro):
        """
        Schedule coroutine as task in event loop thread.

        This method runs in the event loop thread and creates a task
        for the given coroutine with minimal overhead.

        Args:
            coro: Coroutine to schedule
        """
        self.loop.create_task(coro)  # type: ignore

    def _build_scope(
        self,
        method: str,
        path: str,
        headers: list[tuple[str, str]],
        body: bytes,
        server_address: tuple[str, int] = ("127.0.0.1", 8000),
        client_address: tuple[str, int] = ("127.0.0.1", 0),
        is_https: bool = False,
    ) -> dict[str, Any]:
        """
        Build an ASGI scope dictionary from the request data.

        Args:
            method: HTTP method
            path: Request path with query string
            headers: List of header tuples
            body: Request body as bytes
            server_address: Server (host, port) tuple
            client_address: Client (host, port) tuple
            is_https: Whether connection uses HTTPS

        Returns:
            ASGI scope dictionary
        """
        # Parse the URL
        url_parts = urlsplit(path)
        path_only = unquote(url_parts.path) or "/"
        query_string = (url_parts.query or "").encode("utf-8")

        # Determine scheme and extract proxy headers
        scheme = "https" if is_https else "http"
        real_client_address = client_address

        for header_name, header_value in headers:
            header_lower = header_name.lower()
            if header_lower == "x-forwarded-proto":
                scheme = header_value.lower()
            elif header_lower == "x-forwarded-for":
                # Extract real client IP from X-Forwarded-For
                forwarded_ips = header_value.split(",")
                if forwarded_ips:
                    real_ip = forwarded_ips[0].strip()
                    if ":" in real_ip and not real_ip.startswith("["):
                        # IPv4 with port
                        try:
                            ip, port = real_ip.rsplit(":", 1)
                            real_client_address = (ip, int(port))
                        except (ValueError, IndexError):
                            real_client_address = (real_ip, 0)
                    else:
                        # Just IP, no port
                        real_client_address = (real_ip, 0)
            elif header_lower == "x-real-ip":
                # Alternative header for real client IP
                real_client_address = (header_value, 0)

        # Convert headers to ASGI format (lowercase name, bytes value)
        asgi_headers = []
        for header_name, header_value in headers:
            asgi_headers.append((header_name.lower().encode("latin-1"), header_value.encode("latin-1")))

        # Build the ASGI scope
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": scheme,
            "path": path_only,
            "query_string": query_string,
            "root_path": self.root_path,
            "headers": asgi_headers,
            "server": server_address,
            "client": real_client_address,
            "state": {},  # Connection state
        }

        return scope

    async def _handle_request_async(
        self,
        sender,
        method: str,
        path: str,
        headers: list[tuple[str, str]],
        body: bytes,
        request_receiver=None,
    ) -> None:
        """
        Async handler for the request (runs in event loop thread).

        This coroutine is executed in the dedicated event loop thread,
        allowing true concurrent request processing.
        """
        # Build ASGI scope
        scope = self._build_scope(method, path, headers, body)

        # Track response state
        response_started = False
        response_sent = False
        response_status = 500
        response_headers = []
        response_body = []

        # Create receive callable for full-duplex or half-duplex mode
        if request_receiver is not None:
            # Full-duplex mode: stream request body chunks
            async def receive():
                """Receive chunks from RequestReceiver in async context."""
                # Run blocking receive_chunk in executor
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, request_receiver.receive_chunk)

                if result is not None:
                    chunk_data, more_body = result
                    return {
                        "type": "http.request",
                        "body": bytes(chunk_data),
                        "more_body": more_body,
                    }
                else:
                    # No more chunks
                    return {
                        "type": "http.request",
                        "body": b"",
                        "more_body": False,
                    }

        else:
            # Half-duplex mode: use pre-collected body
            body_sent = False

            async def receive():
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {
                        "type": "http.request",
                        "body": body,
                        "more_body": False,
                    }
                else:
                    # No more body
                    return {
                        "type": "http.request",
                        "body": b"",
                        "more_body": False,
                    }

        # Create send callable
        async def send(message: dict[str, Any]):
            nonlocal response_started, response_sent, response_status, response_headers, response_body

            match message["type"]:
                case "http.response.start":
                    if response_started:
                        raise RuntimeError("Response already started")

                    response_started = True
                    response_status = message["status"]

                    # Convert headers from ASGI format (bytes) to string tuples
                    for header_name, header_value in message.get("headers", []):
                        response_headers.append(
                            (
                                header_name.decode("latin-1"),
                                header_value.decode("latin-1"),
                            )
                        )

                    # If sender supports streaming, send start immediately
                    if hasattr(sender, "is_streaming") and sender.is_streaming():
                        sender.send_start(response_status, response_headers)

                case "http.response.body":
                    if not response_started:
                        raise RuntimeError("Response not started")

                    body_chunk = message.get("body", b"")
                    more_body = message.get("more_body", False)

                    # If sender supports streaming, send chunk immediately
                    if hasattr(sender, "is_streaming") and sender.is_streaming():
                        if body_chunk or not more_body:  # Send if has data or last chunk
                            sender.send_chunk(body_chunk, more_body)
                        response_sent = not more_body
                    else:
                        # Legacy mode: buffer all chunks
                        if body_chunk:
                            response_body.append(body_chunk)

                        # Check if this is the last chunk
                        if not more_body:
                            # Only send response if not already sent
                            if not response_sent:
                                response_sent = True
                                full_body = b"".join(response_body)
                                sender.send_response(
                                    response_status,
                                    response_headers,
                                    full_body,
                                    None,
                                )

                case "http.disconnect":
                    # Client disconnected
                    pass

        try:
            # Call the ASGI application
            await self.asgi_app(scope, receive, send)

            # If no response was sent, send an error
            if not response_sent:
                response_sent = True
                sender.send_response(
                    500,
                    [("Content-Type", "text/plain")],
                    b"ASGI application did not send a response",
                    None,
                )

        except Exception as e:
            # If response wasn't sent, we can send an error response
            if not response_sent:
                response_sent = True
                error_body = f"ASGI Error: {str(e)}".encode("utf-8")
                sender.send_response(
                    500,
                    [("Content-Type", "text/plain; charset=utf-8")],
                    error_body,
                    None,
                )
            else:
                # Response already sent, just log the error
                print(f"Error after response sent: {e}", file=sys.stderr)

    def _run_lifespan_startup(self) -> None:
        """Run ASGI lifespan startup protocol."""
        if self.loop is None:
            return

        async def lifespan_startup():
            """ASGI lifespan startup coroutine."""
            self.lifespan_startup_complete = asyncio.Event()
            self.lifespan_shutdown_complete = asyncio.Event()

            scope = {
                "type": "lifespan",
                "asgi": {"version": "3.0"},
            }

            startup_sent = False
            shutdown_sent = False

            async def receive():
                nonlocal startup_sent, shutdown_sent
                if not startup_sent:
                    startup_sent = True
                    return {"type": "lifespan.startup"}
                elif not shutdown_sent:
                    # Wait for shutdown signal
                    await self.lifespan_shutdown_complete.wait()  # type: ignore
                    shutdown_sent = True
                    return {"type": "lifespan.shutdown"}
                else:
                    # Keep receiving after shutdown
                    await asyncio.sleep(float("inf"))

            async def send(message):
                match message["type"]:
                    case "lifespan.startup.complete":
                        self.lifespan_started = True
                        self.lifespan_startup_complete.set()  # type: ignore
                        print("[ASGI Lifespan] Startup complete", file=sys.stderr)
                    case "lifespan.startup.failed":
                        error = message.get("message", "Unknown error")
                        print(f"[ASGI Lifespan] Startup failed: {error}", file=sys.stderr)
                        self.lifespan_startup_complete.set()  # type: ignore
                    case "lifespan.shutdown.complete":
                        self.lifespan_shutdown = True
                        print("[ASGI Lifespan] Shutdown complete", file=sys.stderr)
                    case "lifespan.shutdown.failed":
                        error = message.get("message", "Unknown error")
                        print(f"[ASGI Lifespan] Shutdown failed: {error}", file=sys.stderr)

            try:
                # Run lifespan as background task
                self.lifespan_task = asyncio.create_task(self.asgi_app(scope, receive, send))
                # Wait for startup to complete (with short timeout)
                await asyncio.wait_for(
                    self.lifespan_startup_complete.wait(),
                    timeout=3.0,  # type: ignore
                )
            except asyncio.TimeoutError:
                # App doesn't support lifespan or takes too long - that's ok
                # Don't print warning for apps without lifespan support
                pass
            except Exception:
                # App doesn't support lifespan, that's ok
                # Silently ignore - most simple apps don't need lifespan
                pass

        # Submit lifespan startup to event loop
        future = asyncio.run_coroutine_threadsafe(lifespan_startup(), self.loop)
        try:
            future.result(timeout=5.0)  # Wait for startup with short timeout
        except Exception:
            # Lifespan not supported or failed - that's ok for simple apps
            # Silently continue
            pass

    def shutdown(self) -> None:
        """
        Shutdown the event loop worker.

        This stops the event loop and joins the thread.
        """
        # Trigger lifespan shutdown
        if self.lifespan_shutdown_complete:
            self.lifespan_shutdown_complete.set()  # type: ignore
            # Wait for lifespan task to complete
            if self.lifespan_task and not self.lifespan_task.done():
                try:
                    asyncio.run_coroutine_threadsafe(
                        asyncio.wait_for(self.lifespan_task, timeout=5.0),
                        self.loop,  # type: ignore
                    ).result(timeout=6.0)
                except Exception as e:
                    print(f"[ASGI Lifespan] Shutdown error: {e}", file=sys.stderr)

        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5.0)
