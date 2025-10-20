#!/usr/bin/env python
"""
Example of mounting multiple WSGI applications with the high-performance server.

This demonstrates how to serve multiple Flask apps at different paths.
"""

from flask import Flask, jsonify, request

# Create main application
main_app = Flask(__name__, static_url_path="/static", static_folder=None)


@main_app.route("/")
def main_index():
    return """
    <html>
    <body>
        <h1>Main Application</h1>
        <p>This is the main application serving at /</p>
        <ul>
            <li><a href="/api">API Application</a></li>
            <li><a href="/admin">Admin Application</a></li>
            <li><a href="/blog">Blog Application</a></li>
        </ul>
    </body>
    </html>
    """


@main_app.route("/about")
def main_about():
    return "<h1>About Main App</h1><p>This is the main application.</p>"


# Create API application
api_app = Flask(__name__)


@api_app.route("/")
def api_index():
    return jsonify(
        {
            "service": "API",
            "version": "1.0",
            "endpoints": ["/users", "/posts", "/comments"],
        }
    )


@api_app.route("/users")
def api_users():
    return jsonify(
        {
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"},
                {"id": 3, "name": "Charlie"},
            ]
        }
    )


@api_app.route("/posts")
def api_posts():
    return jsonify(
        {
            "posts": [
                {"id": 1, "title": "First Post", "author_id": 1},
                {"id": 2, "title": "Second Post", "author_id": 2},
            ]
        }
    )


@api_app.route("/echo", methods=["POST"])
def api_echo():
    data = request.get_json()
    return jsonify({"echo": data})


# Create admin application
admin_app = Flask(__name__)


@admin_app.route("/")
def admin_index():
    return """
    <html>
    <body>
        <h1>Admin Panel</h1>
        <p>Administration interface</p>
        <ul>
            <li><a href="/admin/users">Manage Users</a></li>
            <li><a href="/admin/settings">Settings</a></li>
            <li><a href="/admin/logs">View Logs</a></li>
        </ul>
    </body>
    </html>
    """


@admin_app.route("/users")
def admin_users():
    return "<h1>User Management</h1><p>Manage system users here.</p>"


@admin_app.route("/settings")
def admin_settings():
    return "<h1>System Settings</h1><p>Configure system settings.</p>"


@admin_app.route("/logs")
def admin_logs():
    return """
    <h1>System Logs</h1>
    <pre>
    [2025-09-20 10:00:00] System started
    [2025-09-20 10:00:01] Admin logged in
    [2025-09-20 10:00:05] API request received
    </pre>
    """


# Create blog application
blog_app = Flask(__name__)


@blog_app.route("/")
def blog_index():
    return """
    <html>
    <body>
        <h1>Blog</h1>
        <h2>Recent Posts</h2>
        <ul>
            <li><a href="/blog/post/1">Introduction to Multi-App Serving</a></li>
            <li><a href="/blog/post/2">High-Performance Python Servers</a></li>
            <li><a href="/blog/post/3">WSGI and ASGI Explained</a></li>
        </ul>
    </body>
    </html>
    """


@blog_app.route("/post/<int:post_id>")
def blog_post(post_id):
    posts = {
        1: (
            "Introduction to Multi-App Serving",
            "Learn how to serve multiple WSGI applications from a single server.",
        ),
        2: (
            "High-Performance Python Servers",
            "Explore techniques for building fast Python web servers.",
        ),
        3: (
            "WSGI and ASGI Explained",
            "Understanding the difference between WSGI and ASGI protocols.",
        ),
    }

    if post_id in posts:
        title, content = posts[post_id]
        return f"""
        <html>
        <body>
            <h1>{title}</h1>
            <p>{content}</p>
            <a href="/blog">Back to Blog</a>
        </body>
        </html>
        """
    else:
        return "<h1>404 - Post Not Found</h1>", 404


def main():
    """Run multiple WSGI apps using the high-performance server."""

    print("Starting multi-app WSGI server with high-performance transport...")
    print("Applications mounted at:")
    print("  http://localhost:8000/        - Main Application")
    print("  http://localhost:8000/api     - API Application")
    print("  http://localhost:8000/admin   - Admin Application")
    print("  http://localhost:8000/blog    - Blog Application")

    from tsuno import serve

    # Mount all applications using dictionary syntax
    serve(
        {"/": main_app, "/api": api_app, "/admin": admin_app, "/blog": blog_app},
        address="0.0.0.0:8000",
        workers=1,
    )


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

    # Use the dictionary syntax (simpler)
    main()
