"""
WSGI adapter for serving WSGI applications with the high-performance Rust server.

This module provides compatibility with standard WSGI applications (Flask, Django, etc.)
while leveraging the performance benefits of the Rust-based transport layer.
"""

import io
import sys
from typing import Any, Callable
from urllib.parse import unquote, urlsplit


class WSGIAdapter:
    """Adapter to serve WSGI applications using the high-performance server."""

    def __init__(self, wsgi_app: Callable):
        """
        Initialize the WSGI adapter.

        Args:
            wsgi_app: A WSGI application callable
        """
        self.wsgi_app = wsgi_app

    def _build_environ(
        self,
        method: str,
        path: str,
        headers: list[tuple[str, str]],
        body: bytes,
        server_address: tuple[str, int] = ("127.0.0.1", 8000),
        client_address: tuple[str, int] | None = None,
        is_https: bool = False,
    ) -> dict[str, Any]:
        """
        Build a WSGI environ dictionary from the request data.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path with query string
            headers: List of header tuples
            body: Request body as bytes
            server_address: Server (host, port) tuple

        Returns:
            WSGI environ dictionary
        """
        # Parse the URL
        url_parts = urlsplit(path)
        path_info = unquote(url_parts.path) or "/"
        query_string = url_parts.query or ""

        # Determine initial URL scheme
        url_scheme = "https" if is_https else "http"

        # Extract client address
        client_host = "127.0.0.1"
        client_port = "0"
        if client_address:
            client_host = client_address[0]
            client_port = str(client_address[1])

        # Create the base environ
        environ = {
            # WSGI required variables
            "REQUEST_METHOD": method,
            "SCRIPT_NAME": "",
            "PATH_INFO": path_info,
            "QUERY_STRING": query_string,
            "CONTENT_TYPE": "",
            "CONTENT_LENGTH": "",
            "SERVER_NAME": server_address[0],
            "SERVER_PORT": str(server_address[1]),
            "SERVER_PROTOCOL": "HTTP/1.1",
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": url_scheme,
            "wsgi.input": io.BytesIO(body),
            "wsgi.errors": sys.stderr,
            "wsgi.multithread": True,
            "wsgi.multiprocess": True,
            "wsgi.run_once": False,
            # Additional CGI variables
            "REMOTE_ADDR": client_host,
            "REMOTE_HOST": client_host,
            "REMOTE_PORT": client_port,
            "HTTP_HOST": f"{server_address[0]}:{server_address[1]}",
        }

        # Process headers
        content_length = len(body) if body else 0
        for header_name, header_value in headers:
            header_name_upper = header_name.upper()

            if header_name_upper == "CONTENT-TYPE":
                environ["CONTENT_TYPE"] = header_value
            elif header_name_upper == "CONTENT-LENGTH":
                environ["CONTENT_LENGTH"] = header_value
            else:
                # Convert to CGI format: "Header-Name" -> "HTTP_HEADER_NAME"
                key = f"HTTP_{header_name_upper.replace('-', '_')}"
                environ[key] = header_value

                # Special cases
                if header_name_upper == "HOST":
                    environ["HTTP_HOST"] = header_value
                    # Update server name/port from Host header
                    if ":" in header_value:
                        host, port = header_value.rsplit(":", 1)
                        environ["SERVER_NAME"] = host
                        try:
                            environ["SERVER_PORT"] = str(int(port))
                        except ValueError:
                            pass
                    else:
                        environ["SERVER_NAME"] = header_value
                elif header_name_upper == "X-FORWARDED-PROTO":
                    # X-Forwarded-Proto indicates HTTPS behind proxy
                    environ["wsgi.url_scheme"] = header_value.lower()
                    if header_value.lower() == "https":
                        environ["HTTPS"] = "on"
                elif header_name_upper == "X-FORWARDED-FOR":
                    # Extract real client IP from X-Forwarded-For
                    # Format: client, proxy1, proxy2, ...
                    forwarded_ips = header_value.split(",")
                    if forwarded_ips:
                        real_ip = forwarded_ips[0].strip()
                        environ["REMOTE_ADDR"] = real_ip
                        environ["HTTP_X_FORWARDED_FOR"] = header_value
                elif header_name_upper == "X-REAL-IP":
                    # Alternative header for real client IP
                    environ["REMOTE_ADDR"] = header_value
                    environ["HTTP_X_REAL_IP"] = header_value
                elif header_name_upper == "X-FORWARDED-HOST":
                    # Original host requested by client
                    environ["HTTP_X_FORWARDED_HOST"] = header_value

        # Set content length if not provided
        if not environ["CONTENT_LENGTH"]:
            environ["CONTENT_LENGTH"] = str(content_length)

        # Set HTTPS variable if scheme is https
        if environ["wsgi.url_scheme"] == "https" and "HTTPS" not in environ:
            environ["HTTPS"] = "on"

        return environ

    def handle_request(
        self,
        sender,  # ResponseSender from Rust
        method: str,
        path: str,
        headers: list[tuple[str, str]],
        body: bytes,
        request_receiver=None,  # Optional RequestReceiver (not used in WSGI)
    ) -> None:
        """
        Handle an HTTP request by calling the WSGI application.

        Args:
            sender: ResponseSender object from Rust to send the response
            method: HTTP method
            path: Request path
            headers: Request headers
            body: Request body
        """
        # Build WSGI environ
        environ = self._build_environ(method, path, headers, body)

        # Prepare response collection
        response_started = False
        response_status = 500
        response_headers = []
        response_body = []

        def start_response(
            status: str,
            headers: list[tuple[str, str]],
            exc_info: tuple | None = None,
        ) -> Callable:
            """WSGI start_response callable."""
            nonlocal response_started, response_status, response_headers

            if exc_info:
                try:
                    if response_started:
                        raise exc_info[1].with_traceback(exc_info[2])
                finally:
                    exc_info = None
            elif response_started:
                raise RuntimeError("Response already started")

            response_started = True
            # Parse status code from status string (e.g., "200 OK" -> 200)
            try:
                response_status = int(status.split()[0])
            except (ValueError, IndexError):
                response_status = 500

            response_headers = headers

            # Return a write callable (rarely used in modern WSGI apps)
            def write(data: bytes) -> None:
                nonlocal response_body
                if not response_started:
                    raise RuntimeError("write() before start_response()")
                response_body.append(data)

            return write

        try:
            # Call the WSGI application
            app_iter = self.wsgi_app(environ, start_response)

            # Collect response body
            try:
                for data in app_iter:
                    if data:
                        response_body.append(data)
            finally:
                # Close the iterator if it has a close method
                if hasattr(app_iter, "close"):
                    app_iter.close()

            # Combine response body
            full_body = b"".join(response_body)

            # Send response via ResponseSender
            sender.send_response(response_status, response_headers, full_body, None)

        except Exception as e:
            # Send error response if something went wrong
            if not response_started:
                error_body = f"Internal Server Error: {str(e)}".encode("utf-8")
                sender.send_response(
                    500,
                    [("Content-Type", "text/plain; charset=utf-8")],
                    error_body,
                    None,
                )
            else:
                # If response already started, we can't change the status
                # This usually means the client disconnected - silently ignore
                # Only log if it's not a connection error
                if "Failed to send" not in str(e):
                    print(f"Error after response started: {e}", file=sys.stderr)
