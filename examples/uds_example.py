#!/usr/bin/env python3
"""
Unix Domain Socket (UDS) Example

This example demonstrates how to use Tsuno with Unix domain sockets.
UDS is useful for:
- Inter-process communication on the same host
- Better performance than TCP for local connections
- Nginx/reverse proxy integration
- Systemd socket activation

Usage:
    # Method 1: Using tsuno.run() API
    python examples/uds_example.py

    # Method 2: Using CLI with --uds
    tsuno examples.uds_example:application --uds /tmp/tsuno.sock

    # Method 3: Using CLI with --bind unix:
    tsuno examples.uds_example:application --bind unix:/tmp/tsuno.sock

    # Test with curl
    curl --unix-socket /tmp/tsuno.sock http://localhost/
"""

from tsuno import run


def application(environ, start_response):
    """Simple WSGI application"""
    status = "200 OK"
    headers = [
        ("Content-Type", "text/plain"),
        ("X-Server", "tsuno"),
    ]
    start_response(status, headers)

    response = f"""Hello from Tsuno via Unix Domain Socket!

Request Details:
- Method: {environ["REQUEST_METHOD"]}
- Path: {environ["PATH_INFO"]}
- Query String: {environ.get("QUERY_STRING", "")}
- Server Protocol: {environ["SERVER_PROTOCOL"]}

Unix Socket Path: {environ.get("SERVER_NAME", "N/A")}
"""
    return [response.encode("utf-8")]


if __name__ == "__main__":
    import sys

    socket_path = "/tmp/tsuno.sock"

    if len(sys.argv) > 1:
        socket_path = sys.argv[1]

    print(f"Starting Tsuno server on Unix socket: {socket_path}")
    print(f"Test with: curl --unix-socket {socket_path} http://localhost/")
    print()

    run(
        application,
        uds=socket_path,
        interface="wsgi",
        blocking_threads=2,
        log_level="INFO",
    )
