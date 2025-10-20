#!/usr/bin/env python3
"""
Mixed WSGI/ASGI Application Example

This demonstrates Tsuno server's ability to serve both WSGI (Flask) and ASGI (FastAPI)
applications simultaneously on the same server, with automatic protocol detection.

Use case: Add modern async REST API (FastAPI) to existing Flask application without
replacing the entire stack.

Architecture:
- Flask (WSGI) serves traditional web pages at / and /admin
- FastAPI (ASGI) serves REST API at /api
- Single Tsuno server handles both protocols transparently
"""

from fastapi import FastAPI
from flask import Flask, jsonify
from pydantic import BaseModel

# ============================================================================
# Flask Application (WSGI)
# ============================================================================

flask_app = Flask(__name__)


@flask_app.route("/")
def flask_index():
    """Main landing page served by Flask."""
    return """
    <html>
    <head>
        <title>Mixed WSGI/ASGI Application</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; }
            h1 { color: #333; }
            .section { margin: 20px 0; padding: 15px; background: #f5f5f5; border-radius: 5px; }
            a { color: #0066cc; text-decoration: none; }
            a:hover { text-decoration: underline; }
            .wsgi { border-left: 4px solid #4CAF50; }
            .asgi { border-left: 4px solid #2196F3; }
        </style>
    </head>
    <body>
        <h1>Mixed WSGI/ASGI Application Demo</h1>
        <p>This single Tsuno server hosts both Flask (WSGI) and FastAPI (ASGI) applications!</p>

        <div class="section wsgi">
            <h2>🐍 Flask Endpoints (WSGI)</h2>
            <ul>
                <li><a href="/">Main Page</a> - This page</li>
                <li><a href="/flask/hello">Hello Endpoint</a> - Simple Flask response</li>
                <li><a href="/admin">Admin Panel</a> - Flask admin interface</li>
            </ul>
        </div>

        <div class="section asgi">
            <h2>⚡ FastAPI Endpoints (ASGI)</h2>
            <ul>
                <li><a href="/api">API Info</a> - API information</li>
                <li><a href="/api/status">Status</a> - Server status</li>
                <li><a href="/api/items">Items List</a> - GET all items</li>
                <li><a href="/api/docs">API Documentation</a> - Auto-generated OpenAPI docs</li>
            </ul>
        </div>

        <div class="section">
            <h3>🔧 Testing</h3>
            <pre>
# GET request to Flask
curl http://localhost:8000/flask/hello

# GET request to FastAPI
curl http://localhost:8000/api/status

# POST request to FastAPI
curl -X POST http://localhost:8000/api/items \\
  -H "Content-Type: application/json" \\
  -d '{"name": "Test Item", "price": 9.99}'
            </pre>
        </div>
    </body>
    </html>
    """


@flask_app.route("/flask/hello")
def flask_hello():
    """Simple Flask JSON response."""
    return jsonify(
        {
            "message": "Hello from Flask!",
            "protocol": "WSGI",
            "framework": "Flask",
        }
    )


# ============================================================================
# Flask Admin Application (WSGI)
# ============================================================================

admin_app = Flask(__name__)


@admin_app.route("/")
def admin_index():
    """Admin panel main page."""
    return """
    <html>
    <body>
        <h1>Admin Panel</h1>
        <p>This is a separate Flask application mounted at /admin</p>
        <ul>
            <li><a href="/admin/users">User Management</a></li>
            <li><a href="/admin/settings">Settings</a></li>
            <li><a href="/">Back to Main Page</a></li>
        </ul>
    </body>
    </html>
    """


@admin_app.route("/users")
def admin_users():
    """User management endpoint."""
    return jsonify(
        {
            "admin_section": "users",
            "users": [
                {"id": 1, "name": "Alice", "role": "admin"},
                {"id": 2, "name": "Bob", "role": "user"},
            ],
        }
    )


@admin_app.route("/settings")
def admin_settings():
    """Settings endpoint."""
    return jsonify(
        {
            "admin_section": "settings",
            "server": "tsuno",
            "protocol": "WSGI",
            "max_workers": 7,
        }
    )


# ============================================================================
# FastAPI Application (ASGI)
# ============================================================================

fastapi_app = FastAPI(
    title="Mixed App API",
    description="FastAPI running alongside Flask on the same Tsuno server",
    version="1.0.0",
)


# Pydantic models
class Item(BaseModel):
    name: str
    price: float
    description: str | None = None


class ItemResponse(BaseModel):
    id: int
    name: str
    price: float
    description: str | None = None


# In-memory storage for demo
items_db = [
    {"id": 1, "name": "Widget", "price": 9.99, "description": "A useful widget"},
    {"id": 2, "name": "Gadget", "price": 19.99, "description": "An amazing gadget"},
]


@fastapi_app.get("/")
async def api_root():
    """API information endpoint."""
    return {
        "service": "Mixed WSGI/ASGI API",
        "protocol": "ASGI",
        "framework": "FastAPI",
        "endpoints": {
            "status": "/api/status",
            "items": "/api/items",
            "docs": "/api/docs",
        },
    }


@fastapi_app.get("/status")
async def api_status():
    """API status check."""
    return {
        "status": "healthy",
        "protocol": "ASGI",
        "framework": "FastAPI",
        "async_support": True,
    }


@fastapi_app.get("/items", response_model=list[ItemResponse])
async def get_items():
    """Get all items."""
    return items_db


@fastapi_app.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int):
    """Get a specific item by ID."""
    for item in items_db:
        if item["id"] == item_id:
            return item
    return {"error": "Item not found"}


@fastapi_app.post("/items", response_model=ItemResponse)
async def create_item(item: Item):
    """Create a new item."""
    new_item = {
        "id": len(items_db) + 1,
        "name": item.name,
        "price": item.price,
        "description": item.description,
    }
    items_db.append(new_item)
    return new_item


# ============================================================================
# Server Setup
# ============================================================================


def main():
    """Run both Flask and FastAPI applications on a single Tsuno server."""
    from tsuno import serve

    print("=" * 70)
    print("Mixed WSGI/ASGI Application Server")
    print("=" * 70)
    print("\nMounting applications:")
    print("  /         → Flask (WSGI) - Main application")
    print("  /admin    → Flask (WSGI) - Admin panel")
    print("  /api      → FastAPI (ASGI) - REST API")
    print("\nServer starting on http://localhost:8000")
    print("\nKey features demonstrated:")
    print("  ✓ WSGI and ASGI on same server")
    print("  ✓ Automatic protocol detection")
    print("  ✓ Path-based routing")
    print("  ✓ No protocol conversion overhead")
    print("=" * 70)
    print()

    # Mount both WSGI (Flask) and ASGI (FastAPI) apps on the same server
    serve(
        {
            "/": flask_app,  # WSGI
            "/admin": admin_app,  # WSGI
            "/api": fastapi_app,  # ASGI
        },
        address="0.0.0.0:8000",
        workers=1,
        blocking_threads=2,
    )


if __name__ == "__main__":
    # Check if dependencies are installed
    try:
        import fastapi  # noqa: F401
        import flask  # noqa: F401
        import pydantic  # noqa: F401
    except ImportError:
        print("Required dependencies not installed. Please install with:")
        print("  pip install flask fastapi pydantic")
        print("or")
        print("  uv pip install flask fastapi pydantic")
        exit(1)

    main()
