"""Type stubs for pyhtransport module."""

from typing import Callable, Optional

class DedicatedThreadServer:
    """HTTP server with dedicated thread pool for handling requests."""

    def __init__(
        self,
        blocking_threads: Optional[int] = None,
        keepalive: Optional[int] = None,
        limit_concurrency: Optional[int] = None,
    ) -> None:
        """
        Initialize dedicated thread server.

        Args:
            blocking_threads: Number of blocking threads for Python handlers (default: 4)
            keepalive: HTTP keep-alive timeout in seconds (default: 5)
            limit_concurrency: Maximum concurrent connections, None = unlimited (default: None)
        """
        ...

    def serve_fd(
        self,
        socket_fd: int,
        handler: Callable[
            [
                ResponseSender,
                str,
                str,
                list[tuple[str, str]],
                bytes,
                Optional[RequestReceiver],
            ],
            None,
        ],
    ) -> None:
        """
        Start server on inherited file descriptor (for systemd socket activation).

        Args:
            socket_fd: File descriptor of the socket
            handler: Request handler function
        """
        ...

    def serve_uds(
        self,
        socket_path: str,
        handler: Callable[
            [
                ResponseSender,
                str,
                str,
                list[tuple[str, str]],
                bytes,
                Optional[RequestReceiver],
            ],
            None,
        ],
    ) -> None:
        """
        Start server on Unix domain socket.

        Args:
            socket_path: Path to Unix socket file (e.g., "/tmp/app.sock")
            handler: Request handler function
        """
        ...

class ResponseSender:
    """Response sender for streaming HTTP responses."""

    def send_response(
        self,
        status: int,
        headers: list[tuple[str, str]],
        body: bytes,
        trailers: Optional[list[tuple[str, str]]] = None,
    ) -> None:
        """
        Send complete HTTP response at once (convenience method).

        Internally uses streaming protocol: send_start() + send_chunk() + send_trailers().

        Args:
            status: HTTP status code (e.g., 200, 404)
            headers: List of (name, value) header tuples
            body: Response body bytes
            trailers: Optional HTTP trailers (for HTTP/2 or chunked HTTP/1.1)
        """
        ...

    def send_start(self, status: int, headers: list[tuple[str, str]]) -> None:
        """
        Start HTTP response with status and headers (streaming mode).

        Must be called before send_chunk(). Can only be called once.

        Args:
            status: HTTP status code
            headers: List of (name, value) header tuples

        Raises:
            RuntimeError: If response already started
        """
        ...

    def send_chunk(self, data: bytes, more_body: bool) -> None:
        """
        Send response body chunk (streaming mode).

        Can be called multiple times to stream response incrementally.
        Must be called after send_start().

        Args:
            data: Chunk of response body bytes
            more_body: True if more chunks will follow, False for last chunk

        Raises:
            RuntimeError: If response not started (call send_start() first)
        """
        ...

    def send_trailers(self, trailers: list[tuple[str, str]]) -> None:
        """
        Send HTTP trailers (streaming mode).

        Trailers are sent after the last body chunk. Supported by HTTP/2 and
        chunked HTTP/1.1 transfer encoding.

        Args:
            trailers: List of (name, value) trailer tuples

        Raises:
            RuntimeError: If failed to send trailers
        """
        ...

    def is_streaming(self) -> bool:
        """
        Check if this sender is in streaming mode.

        Returns:
            Always True (all senders use streaming mode now)
        """
        ...

    def is_started(self) -> bool:
        """
        Check if response has been started.

        Returns:
            True if send_start() has been called, False otherwise
        """
        ...

class RequestReceiver:
    """Receiver for streaming request body chunks (client streaming / bidirectional streaming)."""

    def receive_chunk(self) -> Optional[tuple[bytes, bool]]:
        """
        Receive next request body chunk (blocking).

        Blocks until next chunk arrives or stream ends.

        Returns:
            (data, more_body) tuple where:
                - data: Chunk bytes
                - more_body: True if more chunks will follow, False for last chunk
            None if stream ended

        Example:
            while True:
                chunk = receiver.receive_chunk()
                if chunk is None:
                    break  # Stream ended
                data, more_body = chunk
                process_data(data)
                if not more_body:
                    break  # Last chunk
        """
        ...

    def is_closed(self) -> bool:
        """
        Check if receiver channel is closed.

        Returns:
            True if channel is closed, False otherwise
        """
        ...
