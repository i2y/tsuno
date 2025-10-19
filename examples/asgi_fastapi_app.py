#!/usr/bin/env python
"""
Example FastAPI application served using the high-performance ASGI server.

This demonstrates how to use the Rust-based server with FastAPI applications.
"""

import time
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Create FastAPI app
app = FastAPI(title="FastAPI on High-Performance Server", version="1.0.0")


# Pydantic models
class HelloRequest(BaseModel):
    name: str


class HelloResponse(BaseModel):
    message: str
    timestamp: float


class EchoRequest(BaseModel):
    data: Dict
    optional_field: Optional[str] = None


class EchoResponse(BaseModel):
    echo: Dict
    timestamp: float
    received_optional: Optional[str] = None


# Routes
@app.get("/")
async def root():
    """Root endpoint with API documentation links."""
    return {
        "message": "FastAPI running on high-performance ASGI server!",
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
    }


@app.get("/hello")
@app.get("/hello/{name}")
async def hello(name: str = "World"):
    """Simple hello endpoint."""
    return HelloResponse(message=f"Hello, {name}!", timestamp=time.time())


@app.post("/api/hello", response_model=HelloResponse)
async def api_hello(request: HelloRequest):
    """Structured hello endpoint with request/response models."""
    return HelloResponse(message=f"Hello, {request.name}!", timestamp=time.time())


@app.post("/api/echo", response_model=EchoResponse)
async def echo(request: EchoRequest):
    """Echo endpoint that returns the request data."""
    return EchoResponse(
        echo=request.data,
        timestamp=time.time(),
        received_optional=request.optional_field,
    )


@app.get("/api/benchmark")
@app.post("/api/benchmark")
async def benchmark(name: Optional[str] = None, request: Optional[HelloRequest] = None):
    """
    Benchmark endpoint similar to the Connect RPC service.
    Accepts both GET and POST requests.
    """
    if request:
        name = request.name
    elif not name:
        name = "World"

    return {
        "message": f"Hello, {name}!",
        "timestamp": time.time(),
        "server": "z-asgi",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "server": "z-asgi",
        "timestamp": time.time(),
    }


@app.get("/async-test")
async def async_test():
    """Test async capabilities."""
    import asyncio

    # Simulate async operation
    await asyncio.sleep(0.001)  # 1ms sleep

    return {
        "message": "Async operation completed",
        "timestamp": time.time(),
    }


@app.get("/error/{code}")
async def trigger_error(code: int):
    """Test error handling."""
    if code == 404:
        raise HTTPException(status_code=404, detail="Not found")
    elif code == 500:
        raise HTTPException(status_code=500, detail="Internal server error")
    else:
        return {"message": f"No error for code {code}"}


def main():
    """Run the FastAPI app using the high-performance ASGI server."""
    from z import serve

    print("Starting FastAPI app with high-performance ASGI server...")
    print("Visit http://localhost:8000 to see the app")
    print("API documentation available at http://localhost:8000/docs")

    # Use the high-performance server instead of Uvicorn
    serve({"/": app}, address="0.0.0.0:8000", workers=1)


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

    main()
