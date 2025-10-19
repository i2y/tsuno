#!/usr/bin/env python3
"""
Test ASGI Lifespan Events support.

Demonstrates proper startup/shutdown lifecycle management.
"""

import asyncio
import sys

from z import serve


# Simulated database connection
class Database:
    def __init__(self):
        self.connected = False

    async def connect(self):
        print("[DB] Connecting to database...")
        await asyncio.sleep(0.5)  # Simulate connection time
        self.connected = True
        print("[DB] Database connected!")

    async def disconnect(self):
        print("[DB] Disconnecting from database...")
        await asyncio.sleep(0.3)  # Simulate disconnection time
        self.connected = False
        print("[DB] Database disconnected!")


# Global database instance
db = Database()


async def lifespan_app(scope, receive, send):
    """ASGI app with lifespan support."""

    if scope["type"] == "lifespan":
        # Handle lifespan events
        while True:
            message = await receive()

            if message["type"] == "lifespan.startup":
                print("[Lifespan] Received startup event")
                try:
                    # Initialize resources
                    await db.connect()
                    await send({"type": "lifespan.startup.complete"})
                except Exception as e:
                    await send(
                        {
                            "type": "lifespan.startup.failed",
                            "message": str(e),
                        }
                    )
                    return

            elif message["type"] == "lifespan.shutdown":
                print("[Lifespan] Received shutdown event")
                try:
                    # Cleanup resources
                    await db.disconnect()
                    await send({"type": "lifespan.shutdown.complete"})
                except Exception as e:
                    await send(
                        {
                            "type": "lifespan.shutdown.failed",
                            "message": str(e),
                        }
                    )
                return

    elif scope["type"] == "http":
        # Handle HTTP requests
        # Receive request body (not used in this example)
        while True:
            message = await receive()
            if message["type"] == "http.request":
                if not message.get("more_body", False):
                    break

        # Send response
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )

        # Response depends on DB connection status
        if db.connected:
            body = b"Hello! Database is connected and ready.\n"
        else:
            body = b"Warning: Database is not connected!\n"

        await send(
            {
                "type": "http.response.body",
                "body": body,
                "more_body": False,
            }
        )


def main():
    if len(sys.argv) < 4:
        print("Usage: python lifespan_test.py <port> <workers> <threads>")
        print("Example: python lifespan_test.py 8000 1 2")
        sys.exit(1)

    port = int(sys.argv[1])
    workers = int(sys.argv[2])
    threads_per_worker = int(sys.argv[3])

    print(f"Starting ASGI Lifespan test server on port {port}")
    print(f"Configuration: {workers} workers, {threads_per_worker} threads each")
    print("\nLifespan Events:")
    print("  - startup: Database connection initialization")
    print("  - shutdown: Database connection cleanup")
    print("\nTest with:")
    print(f"  curl http://localhost:{port}/")
    print("\nExpected: 'Database is connected and ready'")
    print("=" * 70)
    print()

    # Serve ASGI app (with lifespan support)
    serve(
        {"/": lifespan_app},
        address=f"0.0.0.0:{port}",
        workers=workers,
        blocking_threads=threads_per_worker,
    )


if __name__ == "__main__":
    main()
