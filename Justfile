# z Development Tasks

# Default recipe to display help
default:
    @just --list --unsorted

# Display help
help:
    @echo "z Development Commands"
    @echo "======================================"
    @just --list

# ============== Build Tasks ==============

# Full build (Rust extension only)
build:
    @echo "Building Rust extension..."
    @chmod +x build.sh
    @./build.sh

# Build only the Rust extension
build-rust:
    @echo "Building Rust extension with maturin..."
    cd pyhtransport && uv run maturin develop --release
    @echo "Rust extension build complete!"

# ============== Development Setup ==============

# Install all dependencies
install:
    @echo "Installing all dependencies..."
    uv sync --all-groups

# ============== Test Tasks ==============

# Run all tests
test:
    @echo "Running tests..."
    PYTHONPATH=. uv run pytest tests/ -v

# ============== Code Quality ==============

# Format all code (Python + Rust)
format:
    @echo "Formatting Python code..."
    @uv run black . --exclude ".venv|build|target"
    @uv run isort . --skip .venv --skip build --skip target
    @uv run ruff check . --fix --silent || true
    @echo "Formatting Rust code..."
    @cd pyhtransport && cargo fmt
    @echo "Code formatting complete!"

# Run all linters (Python + Rust)
lint:
    @echo "Linting Python code..."
    @uv run ruff check .
    @echo "Linting Rust code..."
    @cd pyhtransport && cargo clippy -- -W clippy::all
    @echo "Linting complete!"

# ============== Clean Tasks ==============

# Clean all build artifacts
clean:
    @echo "Cleaning Python artifacts..."
    @rm -rf __pycache__ */__pycache__ */*/__pycache__
    @rm -rf *.pyc */*.pyc */*/*.pyc
    @rm -rf .pytest_cache .coverage htmlcov
    @rm -rf dist build *.egg-info
    @echo "Cleaning Rust artifacts..."
    @cd pyhtransport && cargo clean
    @echo "Cleanup complete!"

# ============== Linux Testing (Docker) ==============

# Run Linux compatibility tests in Docker
test-linux:
    @echo "Running Linux tests in Docker..."
    @docker build -f Dockerfile.linux-test -t z-linux-test .
    @docker run --rm z-linux-test bash tests/linux_basic_test.sh

# Run Linux benchmarks in Docker
bench-linux:
    @echo "Running Linux benchmarks in Docker..."
    @docker build -f Dockerfile.linux-test -t z-linux-test .
    @docker run --rm z-linux-test bash tests/linux_benchmark_simple.sh

# Run full Linux test suite (tests + benchmarks)
test-linux-full:
    @echo "Running full Linux test suite in Docker..."
    @docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit

# Run Linux server comparison benchmark (z vs Granian vs Uvicorn vs Hypercorn)
bench-linux-comparison:
    @echo "Running comprehensive server comparison on Linux..."
    @docker build -f Dockerfile.linux-test -t z-linux-test .
    @docker run --rm z-linux-test bash tests/linux_benchmark_comparison.sh
