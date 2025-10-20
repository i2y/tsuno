#!/usr/bin/env python
"""
Example Flask application served using the high-performance WSGI server.

This demonstrates how to use the Rust-based server with existing Flask applications.
"""

import time

from flask import Flask, jsonify, request

# Create Flask app
app = Flask(__name__)


@app.route("/")
def index():
    """Simple index page."""
    return """
    <h1>Flask on High-Performance Server</h1>
    <p>This Flask app is running on the Rust-based high-performance server!</p>
    <ul>
        <li><a href="/hello">Hello endpoint</a></li>
        <li><a href="/api/echo">Echo API (POST)</a></li>
        <li><a href="/api/benchmark">Benchmark endpoint</a></li>
        <li><a href="/health">Health check</a></li>
    </ul>
    """


@app.route("/hello")
@app.route("/hello/<name>")
def hello(name="World"):
    """Simple hello endpoint."""
    return f"Hello, {name}!"


@app.route("/api/echo", methods=["POST"])
def echo():
    """Echo back the JSON request."""
    data = request.get_json() or {}
    return jsonify({"echo": data, "timestamp": time.time()})


@app.route("/api/benchmark", methods=["GET", "POST"])
def benchmark():
    """
    Benchmark endpoint similar to the Connect RPC service.
    Used for performance comparison.
    """
    if request.method == "POST":
        data = request.get_json() or {}
        name = data.get("name", "World")
    else:
        name = request.args.get("name", "World")

    return jsonify({"message": f"Hello, {name}!", "timestamp": time.time()})


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "server": "tsuno-wsgi"})


@app.route("/headers")
def show_headers():
    """Debug endpoint to show request headers."""
    headers = dict(request.headers)
    return jsonify(
        {
            "method": request.method,
            "path": request.path,
            "query": request.query_string.decode(),
            "headers": headers,
        }
    )


def main():
    """Run the Flask app using the high-performance WSGI server."""
    from tsuno import serve

    print("Starting Flask app with high-performance WSGI server...")
    print("Visit http://localhost:5001 to see the app")

    # Use the high-performance server instead of Flask's built-in server
    serve({"/": app}, address="0.0.0.0:5001", workers=1)


if __name__ == "__main__":
    # Check if Flask is installed
    try:
        import flask  # noqa: F401
    except ImportError:
        print("Flask is not installed. Please install it with:")
        print("  pip install flask")
        print("or")
        print("  uv pip install flask")
        exit(1)

    main()
