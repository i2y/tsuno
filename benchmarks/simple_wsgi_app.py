#!/usr/bin/env python3
"""Simple WSGI app for benchmarking (non-streaming)"""


def app(environ, start_response):
    """Simple Hello World WSGI app"""
    status = "200 OK"
    headers = [("Content-type", "text/plain")]
    start_response(status, headers)
    return [b"Hello, World!"]


if __name__ == "__main__":
    import sys

    from z import serve

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    blocking_threads = int(sys.argv[3]) if len(sys.argv) > 3 else 2

    print(f"Starting simple WSGI server on 0.0.0.0:{port}")
    print(f"Workers: {workers}, Blocking threads: {blocking_threads}")
    serve(
        {"/": app},
        address=f"0.0.0.0:{port}",
        workers=workers,
        blocking_threads=blocking_threads,
        access_log=False,  # Disable access logging for benchmarks
        timeout=0,  # Disable timeout monitoring for benchmarks (enables fast path)
    )
