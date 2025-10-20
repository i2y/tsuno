#!/bin/bash
set -e

# Activate virtual environment and set PYTHONPATH
source /app/.venv/bin/activate
export PYTHONPATH=/app:$PYTHONPATH

echo "Linux Simple Benchmark"
echo "Hardware: $(nproc) CPUs"
echo "Kernel: $(uname -r)"
echo ""

# Tsuno single worker benchmark
echo "Benchmarking tsuno (1 worker × 1 thread)..."
export TOKIO_WORKER_THREADS=1
export LOG_LEVEL=ERROR
python benchmarks/simple_asgi_app.py 8000 1 1 &
PID=$!
sleep 7
wrk -t4 -c100 -d10s --latency http://localhost:8000/ | tee results_z_linux.txt
kill $PID
sleep 3
echo ""

# Tsuno multi worker benchmark
WORKERS=$(( $(nproc) / 2 ))
[ $WORKERS -lt 2 ] && WORKERS=2
echo "Benchmarking tsuno ($WORKERS workers × 2 threads)..."
export TOKIO_WORKER_THREADS=1
export LOG_LEVEL=ERROR
python benchmarks/simple_asgi_app.py 8000 $WORKERS 2 &
PID=$!
sleep 7
wrk -t12 -c300 -d10s --latency http://localhost:8000/ | tee results_z_linux_multi.txt
kill $PID
echo ""

echo "Benchmark Results Summary"
echo "Single Worker:"
grep "Requests/sec" results_z_linux.txt
grep "Latency" results_z_linux.txt | head -1
echo ""
echo "Multi Worker ($WORKERS workers):"
grep "Requests/sec" results_z_linux_multi.txt
grep "Latency" results_z_linux_multi.txt | head -1
echo ""
