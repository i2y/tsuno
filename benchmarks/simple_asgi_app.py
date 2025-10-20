#!/usr/bin/env python3
"""Simple ASGI app for benchmarking (non-streaming)"""


async def app(scope, receive, send):
    """Simple Hello World ASGI app"""
    if scope["type"] != "http":
        return

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        }
    )

    await send(
        {
            "type": "http.response.body",
            "body": b"Hello, World!",
            "more_body": False,
        }
    )


if __name__ == "__main__":
    import sys

    from tsuno import serve

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    blocking_threads = int(sys.argv[3]) if len(sys.argv) > 3 else 2

    print(f"Starting simple ASGI server on 0.0.0.0:{port}")
    print(f"Workers: {workers}, Blocking threads: {blocking_threads}")
    serve(
        {"/": app},
        address=f"0.0.0.0:{port}",
        workers=workers,
        blocking_threads=blocking_threads,
        access_log=False,  # Disable access logging for benchmarks
        use_uvloop=True,  # Enable uvloop for maximum performance
        timeout=0,  # Disable timeout monitoring for benchmarks (enables fast path)
    )
