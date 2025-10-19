#!/bin/bash
set -e

# Activate virtual environment and set PYTHONPATH
source /app/.venv/bin/activate
export PYTHONPATH=/app:$PYTHONPATH

echo "Linux Server Comparison Benchmark"
echo "Hardware: $(nproc) CPUs"
echo "Kernel: $(uname -r)"
echo ""

# Install Granian if not present
echo "Installing Granian and Uvicorn..."
uv pip install granian uvicorn[standard] 2>&1 | grep -E "(already|Successfully)" || true
echo ""

# Create standalone ASGI app for other servers
cat > /tmp/simple_asgi_standalone.py << 'EOF'
async def app(scope, receive, send):
    """Simple Hello World ASGI app"""
    if scope["type"] != "http":
        return

    await send({
        "type": "http.response.start",
        "status": 200,
        "headers": [(b"content-type", b"text/plain")],
    })

    await send({
        "type": "http.response.body",
        "body": b"Hello, World!",
        "more_body": False,
    })
EOF

# Single Worker Benchmarks

echo "SINGLE WORKER BENCHMARKS (1w×1t)"
echo ""

# z single worker
echo "1. Benchmarking z (1 worker × 1 thread)..."
export TOKIO_WORKER_THREADS=1
export LOG_LEVEL=ERROR
python benchmarks/simple_asgi_app.py 8000 1 1 &
PID=$!
sleep 7
wrk -t4 -c100 -d10s --latency http://localhost:8000/ 2>&1 | tee /tmp/result_z_1w.txt
kill $PID 2>/dev/null || true
wait $PID 2>/dev/null || true
sleep 5
echo ""

# Granian single worker
echo "2. Benchmarking Granian (1 worker)..."
granian --interface asgi --workers 1 --no-access-log \
  --log-level error \
  /tmp/simple_asgi_standalone:app --host 0.0.0.0 --port 8000 &
PID=$!
sleep 7
wrk -t4 -c100 -d10s --latency http://localhost:8000/ 2>&1 | tee /tmp/result_granian_1w.txt
kill $PID 2>/dev/null || true
wait $PID 2>/dev/null || true
sleep 5
echo ""

# Uvicorn single worker
echo "3. Benchmarking Uvicorn (1 worker with uvloop + httptools)..."
cd /tmp && uvicorn simple_asgi_standalone:app \
  --host 0.0.0.0 --port 8000 \
  --loop uvloop \
  --log-level warning \
  --no-access-log &
PID=$!
cd /app
sleep 7
wrk -t4 -c100 -d10s --latency http://localhost:8000/ 2>&1 | tee /tmp/result_uvicorn_1w.txt
kill $PID 2>/dev/null || true
wait $PID 2>/dev/null || true
sleep 5
echo ""

# Hypercorn single worker
echo "4. Benchmarking Hypercorn (1 worker with uvloop)..."
hypercorn /tmp/simple_asgi_standalone:app \
  --bind 0.0.0.0:8000 \
  --worker-class uvloop \
  --log-level warning \
  --access-log - \
  --access-logfile - &
PID=$!
sleep 7
wrk -t4 -c100 -d10s --latency http://localhost:8000/ 2>&1 | tee /tmp/result_hypercorn_1w.txt
kill $PID 2>/dev/null || true
wait $PID 2>/dev/null || true
pkill -f "hypercorn" 2>/dev/null || true
sleep 8
echo ""

# Multi Worker Benchmarks

echo "MULTI WORKER BENCHMARKS (7w×2t)"
echo ""

# z multi worker
echo "1. Benchmarking z (7 workers × 2 threads)..."
export TOKIO_WORKER_THREADS=1
export LOG_LEVEL=ERROR
python benchmarks/simple_asgi_app.py 8000 7 2 &
PID=$!
sleep 10
wrk -t12 -c300 -d10s --latency http://localhost:8000/ 2>&1 | tee /tmp/result_z_7w.txt
kill $PID 2>/dev/null || true
wait $PID 2>/dev/null || true
pkill -f "simple_asgi_app.py" 2>/dev/null || true
pkill -f "pyhtransport" 2>/dev/null || true
sleep 8
echo ""

# Granian multi worker
echo "2. Benchmarking Granian (7 workers)..."
granian --interface asgi --workers 7 --no-access-log \
  --log-level error \
  /tmp/simple_asgi_standalone:app --host 0.0.0.0 --port 8000 &
PID=$!
sleep 10
wrk -t12 -c300 -d10s --latency http://localhost:8000/ 2>&1 | tee /tmp/result_granian_7w.txt
kill $PID 2>/dev/null || true
wait $PID 2>/dev/null || true
pkill -f "granian" 2>/dev/null || true
sleep 8
echo ""

# Uvicorn multi worker
echo "3. Benchmarking Uvicorn (7 workers with uvloop + httptools)..."
cd /tmp && uvicorn simple_asgi_standalone:app --workers 7 \
  --host 0.0.0.0 --port 8000 \
  --loop uvloop \
  --log-level warning \
  --no-access-log &
PID=$!
cd /app
sleep 10
wrk -t12 -c300 -d10s --latency http://localhost:8000/ 2>&1 | tee /tmp/result_uvicorn_7w.txt
kill $PID 2>/dev/null || true
wait $PID 2>/dev/null || true
pkill -f "uvicorn" 2>/dev/null || true
sleep 8
echo ""

# Hypercorn multi worker
echo "4. Benchmarking Hypercorn (7 workers with uvloop)..."
hypercorn /tmp/simple_asgi_standalone:app --workers 7 \
  --bind 0.0.0.0:8000 \
  --worker-class uvloop \
  --log-level warning \
  --access-log - \
  --access-logfile - &
PID=$!
sleep 10
wrk -t12 -c300 -d10s --latency http://localhost:8000/ 2>&1 | tee /tmp/result_hypercorn_7w.txt
kill $PID 2>/dev/null || true
wait $PID 2>/dev/null || true
pkill -f "hypercorn" 2>/dev/null || true
sleep 8
echo ""

# Results Summary

echo "BENCHMARK RESULTS SUMMARY"
echo ""

echo "--- SINGLE WORKER (1w×1t) ---"
echo ""
echo "z:"
grep "Requests/sec" /tmp/result_z_1w.txt
grep "99%" /tmp/result_z_1w.txt | head -1
echo ""

echo "Granian:"
grep "Requests/sec" /tmp/result_granian_1w.txt
grep "99%" /tmp/result_granian_1w.txt | head -1
echo ""

echo "Uvicorn:"
grep "Requests/sec" /tmp/result_uvicorn_1w.txt
grep "99%" /tmp/result_uvicorn_1w.txt | head -1
echo ""

echo "Hypercorn:"
grep "Requests/sec" /tmp/result_hypercorn_1w.txt
grep "99%" /tmp/result_hypercorn_1w.txt | head -1
echo ""

echo "--- MULTI WORKER (7w×2t) ---"
echo ""
echo "z:"
grep "Requests/sec" /tmp/result_z_7w.txt
grep "99%" /tmp/result_z_7w.txt | head -1
echo ""

echo "Granian:"
grep "Requests/sec" /tmp/result_granian_7w.txt
grep "99%" /tmp/result_granian_7w.txt | head -1
echo ""

echo "Uvicorn:"
grep "Requests/sec" /tmp/result_uvicorn_7w.txt
grep "99%" /tmp/result_uvicorn_7w.txt | head -1
echo ""

echo "Hypercorn:"
grep "Requests/sec" /tmp/result_hypercorn_7w.txt
grep "99%" /tmp/result_hypercorn_7w.txt | head -1
echo ""

echo "Benchmark complete!"
