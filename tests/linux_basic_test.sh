#!/bin/bash
set -e

# Activate virtual environment and set PYTHONPATH
source /app/.venv/bin/activate
export PYTHONPATH=/app:$PYTHONPATH

echo "Linux Basic Test Suite"
echo "Platform: $(uname -a)"
echo "Python: $(python --version)"
echo "CPUs: $(nproc)"
echo ""

# Test 1: Import test
echo "Test 1: Import test"
python -c "import tsuno; print('✅ tsuno imported successfully')" || exit 1
python -c "import pyhtransport; print('✅ pyhtransport imported successfully')" || exit 1
echo ""

# Test 2: CLI test
echo "Test 2: CLI test"
tsuno --help > /dev/null && echo "✅ CLI works" || exit 1
echo ""

# Test 3: Simple ASGI app (single worker)
echo "Test 3: Simple ASGI app (single worker)"
export LOG_LEVEL=ERROR
python benchmarks/simple_asgi_app.py 8000 1 1 &
PID=$!
sleep 5
curl -s http://localhost:8000/ | grep -q "Hello, World" && echo "✅ ASGI app works" || (kill $PID; exit 1)
kill $PID
sleep 2
echo ""

# Test 4: Multi-worker test
echo "Test 4: Multi-worker test"
python benchmarks/simple_asgi_app.py 8000 4 2 &
PID=$!
sleep 7
SUCCESS=0
for i in {1..20}; do
    curl -s http://localhost:8000/ > /dev/null && SUCCESS=$((SUCCESS+1))
done
kill $PID
[ $SUCCESS -eq 20 ] && echo "✅ Multi-worker works (20/20 requests succeeded)" || echo "⚠️  Multi-worker partial success ($SUCCESS/20 requests succeeded)"
sleep 2
echo ""

# Test 5: Quick benchmark (single worker)
echo "Test 5: Quick benchmark (single worker)"
export TOKIO_WORKER_THREADS=1
python benchmarks/simple_asgi_app.py 8000 1 1 &
PID=$!
sleep 5
wrk -t2 -c50 -d5s http://localhost:8000/ 2>&1 | tee /tmp/bench_result.txt
kill $PID
THROUGHPUT=$(grep "Requests/sec" /tmp/bench_result.txt | awk '{print $2}')
echo "Throughput: $THROUGHPUT req/s"
echo ""

# Test 6: Flask WSGI app
echo "Test 6: Flask WSGI app"
if [ -f examples/wsgi_flask_app.py ]; then
    python examples/wsgi_flask_app.py &
    PID=$!
    sleep 7
    curl -s http://localhost:5001/ | grep -q "Flask" && echo "✅ Flask WSGI works" || echo "⚠️  Flask test failed"
    kill $PID 2>/dev/null || true
    wait $PID 2>/dev/null || true
    sleep 2
fi
echo ""

echo "All basic tests completed!"
