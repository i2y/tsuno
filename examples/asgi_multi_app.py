#!/usr/bin/env python
"""
Example of mounting multiple ASGI applications with the high-performance server.

This demonstrates how to serve multiple FastAPI apps at different paths.
"""

import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


# Models for API
class User(BaseModel):
    id: int
    name: str
    email: str


class Post(BaseModel):
    id: int
    title: str
    content: str
    author_id: int


class EchoRequest(BaseModel):
    message: str


# Create main application
main_app = FastAPI(title="Main Application")


@main_app.get("/", response_class=HTMLResponse)
async def main_index():
    return """
    <html>
    <body>
        <h1>Main Application</h1>
        <p>This is the main FastAPI application serving at /</p>
        <ul>
            <li><a href="/docs">Main API Docs</a></li>
            <li><a href="/api">API Service</a></li>
            <li><a href="/api/docs">API Service Docs</a></li>
            <li><a href="/admin">Admin Panel</a></li>
            <li><a href="/admin/docs">Admin API Docs</a></li>
            <li><a href="/metrics">Metrics Service</a></li>
            <li><a href="/metrics/docs">Metrics API Docs</a></li>
        </ul>
    </body>
    </html>
    """


@main_app.get("/health")
async def main_health():
    return {"status": "healthy", "service": "main", "timestamp": time.time()}


@main_app.get("/about")
async def main_about():
    return {"service": "Main Application", "version": "1.0.0"}


# Create API application
api_app = FastAPI(title="API Service", version="2.0.0")


@api_app.get("/")
async def api_index():
    return {
        "service": "API",
        "version": "2.0.0",
        "endpoints": ["/users", "/posts", "/echo"],
    }


@api_app.get("/users", response_model=list[User])
async def api_users():
    return [
        User(id=1, name="Alice", email="alice@example.com"),
        User(id=2, name="Bob", email="bob@example.com"),
        User(id=3, name="Charlie", email="charlie@example.com"),
    ]


@api_app.get("/users/{user_id}", response_model=User)
async def api_user(user_id: int):
    users = {
        1: User(id=1, name="Alice", email="alice@example.com"),
        2: User(id=2, name="Bob", email="bob@example.com"),
        3: User(id=3, name="Charlie", email="charlie@example.com"),
    }
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    return users[user_id]


@api_app.get("/posts", response_model=list[Post])
async def api_posts():
    return [
        Post(id=1, title="First Post", content="This is the first post", author_id=1),
        Post(id=2, title="Second Post", content="This is the second post", author_id=2),
    ]


@api_app.post("/echo")
async def api_echo(request: EchoRequest):
    return {"echo": request.message, "timestamp": time.time()}


# Create admin application
admin_app = FastAPI(title="Admin Panel")


@admin_app.get("/", response_class=HTMLResponse)
async def admin_index():
    return """
    <html>
    <body>
        <h1>Admin Panel</h1>
        <p>Administration interface for system management</p>
        <ul>
            <li><a href="/admin/users">User Management</a></li>
            <li><a href="/admin/settings">System Settings</a></li>
            <li><a href="/admin/logs">View Logs</a></li>
            <li><a href="/admin/stats">Statistics</a></li>
        </ul>
    </body>
    </html>
    """


@admin_app.get("/users")
async def admin_users():
    return {
        "total_users": 3,
        "active_users": 2,
        "suspended_users": 1,
        "last_registration": "2025-09-20T10:30:00Z",
    }


@admin_app.get("/settings")
async def admin_settings():
    return {
        "maintenance_mode": False,
        "max_upload_size": "10MB",
        "session_timeout": 3600,
        "debug_mode": False,
    }


@admin_app.get("/logs")
async def admin_logs():
    return {
        "logs": [
            {
                "timestamp": "2025-09-20T10:00:00Z",
                "level": "INFO",
                "message": "System started",
            },
            {
                "timestamp": "2025-09-20T10:00:01Z",
                "level": "INFO",
                "message": "Admin logged in",
            },
            {
                "timestamp": "2025-09-20T10:00:05Z",
                "level": "INFO",
                "message": "API request received",
            },
            {
                "timestamp": "2025-09-20T10:00:10Z",
                "level": "WARNING",
                "message": "High memory usage detected",
            },
        ]
    }


@admin_app.get("/stats")
async def admin_stats():
    return {
        "cpu_usage": "25%",
        "memory_usage": "45%",
        "disk_usage": "60%",
        "active_connections": 42,
        "requests_per_second": 150,
    }


# Create metrics application
metrics_app = FastAPI(title="Metrics Service")


@metrics_app.get("/")
async def metrics_index():
    return {
        "service": "Metrics",
        "available_metrics": ["/cpu", "/memory", "/requests", "/latency"],
    }


@metrics_app.get("/cpu")
async def metrics_cpu():
    return {"metric": "cpu", "value": 25.5, "unit": "percent", "timestamp": time.time()}


@metrics_app.get("/memory")
async def metrics_memory():
    return {
        "metric": "memory",
        "used": 1024,
        "total": 2048,
        "unit": "MB",
        "timestamp": time.time(),
    }


@metrics_app.get("/requests")
async def metrics_requests():
    return {
        "metric": "requests",
        "total": 1000000,
        "success": 999500,
        "errors": 500,
        "rate": 150,
        "timestamp": time.time(),
    }


@metrics_app.get("/latency")
async def metrics_latency():
    return {
        "metric": "latency",
        "p50": 10,
        "p95": 25,
        "p99": 50,
        "unit": "ms",
        "timestamp": time.time(),
    }


def main():
    """Run multiple ASGI apps using the high-performance server."""

    print("Starting multi-app ASGI server with high-performance transport...")
    print("Applications mounted at:")
    print("  http://localhost:8001/         - Main Application")
    print("  http://localhost:8001/api     - API Service")
    print("  http://localhost:8001/admin   - Admin Panel")
    print("  http://localhost:8001/metrics - Metrics Service")
    print()
    print("API Documentation available at:")
    print("  http://localhost:8001/docs         - Main App Docs")
    print("  http://localhost:8001/api/docs     - API Service Docs")
    print("  http://localhost:8001/admin/docs   - Admin Panel Docs")
    print("  http://localhost:8001/metrics/docs - Metrics Service Docs")

    from tsuno import serve

    # Mount all applications using dictionary syntax
    serve(
        {"/": main_app, "/api": api_app, "/admin": admin_app, "/metrics": metrics_app},
        address="0.0.0.0:8001",
        workers=1,
    )


def main_with_submount():
    """Alternative: Use FastAPI's built-in mount (for comparison)."""
    from tsuno import serve

    # Create a main app and mount sub-apps using FastAPI's mount
    root_app = FastAPI(title="Root Application with Sub-Apps")

    # Mount sub-applications
    root_app.mount("/api", api_app)
    root_app.mount("/admin", admin_app)
    root_app.mount("/metrics", metrics_app)

    # Add a root route
    @root_app.get("/")
    async def root():
        return {"message": "Root app with mounted sub-apps"}

    print("Starting ASGI server with FastAPI's built-in mounting...")
    serve({"/": root_app}, address="0.0.0.0:8001", workers=1)


if __name__ == "__main__":
    # Check if FastAPI is installed
    try:
        import fastapi  # noqa: F401
        import pydantic  # noqa: F401
    except ImportError:
        print("FastAPI or Pydantic is not installed. Please install them with:")
        print("  pip install fastapi pydantic")
        print("or")
        print("  uv pip install fastapi pydantic")
        exit(1)

    # Use the dictionary syntax (simpler)
    main()

    # Or use FastAPI's built-in mounting
    # main_with_submount()
