# Tsuno

**High-performance WSGI/ASGI server powered by Rust**

![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Development Status](https://img.shields.io/badge/status-alpha-orange.svg)

Tsuno aims to be a drop-in replacement for Gunicorn and Uvicorn with a Rust-powered transport layer. Run your Django, Flask, FastAPI, and Starlette applications with HTTP/2 support.

## Installation

```bash
pip install tsuno
```

## Quick Start

### Command Line

```bash
# Replace Gunicorn/Uvicorn
tsuno myapp:app --workers 4 --bind 0.0.0.0:8000
```

### Python API

**Flask (WSGI)**:
```python
from flask import Flask
from tsuno import run

app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello World"

if __name__ == "__main__":
    run(app)
```

**FastAPI (ASGI)**:
```python
from fastapi import FastAPI
from tsuno import run

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}

if __name__ == "__main__":
    run(app)
```

See [`examples/`](examples/) for complete working examples.

## What Makes Tsuno Different

- **Mixed Protocol Serving**: Serve WSGI and ASGI apps simultaneously on the same server ([example](examples/mixed_wsgi_asgi.py))
- **High Performance**: Powered by Tokio and hyper
- **Complete API Compatibility**: Drop-in replacement for both Gunicorn AND Uvicorn as much as possible
- **Unix Domain Sockets**: Full UDS support for nginx integration ([example](examples/uds_example.py))

## Examples

Complete working examples in the [`examples/`](examples/) directory:

| Example | Description |
|---------|-------------|
| **[wsgi_flask_app.py](examples/wsgi_flask_app.py)** | Flask WSGI application |
| **[asgi_fastapi_app.py](examples/asgi_fastapi_app.py)** | FastAPI ASGI application |
| **[mixed_wsgi_asgi.py](examples/mixed_wsgi_asgi.py)** | **Mixed WSGI + ASGI serving** (unique to Tsuno!) |
| **[wsgi_multi_app.py](examples/wsgi_multi_app.py)** | Multiple Flask apps on different paths |
| **[asgi_multi_app.py](examples/asgi_multi_app.py)** | Multiple FastAPI apps on different paths |
| **[uds_example.py](examples/uds_example.py)** | Unix Domain Socket server |
| **[lifespan_test.py](examples/lifespan_test.py)** | ASGI Lifespan events demo |
| **[tsuno.toml](examples/tsuno.toml)** | TOML configuration example |

## Configuration

### Command Line

```bash
# Basic
tsuno myapp:app --bind 0.0.0.0:8000 --workers 4

# With auto-reload (development)
tsuno myapp:app --reload

# With Unix domain socket
tsuno myapp:app --uds /tmp/tsuno.sock

# With configuration file
tsuno myapp:app -c tsuno.toml
```

### Configuration File

**Python format** (Gunicorn-compatible):
```python
# tsuno.conf.py
bind = "0.0.0.0:8000"
workers = 4
threads = 2
log_level = "info"
```

**TOML format**:
```toml
# tsuno.toml
bind = "0.0.0.0:8000"
workers = 4
threads = 2
log_level = "info"
```

See [examples/tsuno.toml](examples/tsuno.toml) for all options.

### Python API

```python
from tsuno import run

run(
    app,
    host="0.0.0.0",
    port=8000,
    workers=4,
    reload=True,  # Development only
)
```

## Production Features

### Worker Management
- Auto-restart crashed workers
- Graceful shutdown and reload
- Worker timeout monitoring
- Max requests per worker (memory leak prevention)

### Graceful Reload (Zero-Downtime)

```bash
# Start with PID file
tsuno myapp:app --pid /var/run/tsuno.pid

# Graceful reload (no downtime)
kill -HUP $(cat /var/run/tsuno.pid)
```

### Logging
- Structured logging (text/JSON)
- Access log support
- Customizable log formats

## Performance

Performance varies by workload, platform, and configuration.
Please see [benchmarks/comparison.md](benchmarks/comparison.md) for detailed results and methodology.

## Migration

### From Gunicorn

```bash
# Before
gunicorn myapp:app --workers 4 --bind 0.0.0.0:8000

# After (same syntax!)
tsuno myapp:app --workers 4 --bind 0.0.0.0:8000
```

### From Uvicorn

```python
# Before
import uvicorn
uvicorn.run(app, host="0.0.0.0", port=8000, workers=4)

# After (compatible API!)
import tsuno
tsuno.run(app, host="0.0.0.0", port=8000, workers=4)
```

## Development Status

**Tsuno is in early development (alpha stage)**.

- ⚠️ Real-world production testing needed

**Help us test!** Report issues at [github.com/i2y/tsuno/issues](https://github.com/i2y/tsuno/issues)

## Requirements

- Python 3.11 or later
- Rust toolchain (for building from source)

## License

MIT License - see [LICENSE](LICENSE)

## Links

- **Repository**: [github.com/i2y/tsuno](https://github.com/i2y/tsuno)
- **Issues**: [github.com/i2y/tsuno/issues](https://github.com/i2y/tsuno/issues)
- **Benchmarks**: [benchmarks/comparison.md](benchmarks/comparison.md)

## Acknowledgments

Tsuno is inspired by and builds upon excellent work from:
- **Gunicorn** & **Uvicorn**: Server standards
- **Granian**: Rust-Python hybrid architecture
- **Tokio**, **hyper**, **PyO3**: Rust ecosystem
