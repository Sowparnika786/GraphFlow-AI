import time
import os
import sys
import statistics
import asyncio
from httpx import AsyncClient, ASGITransport

# Add api directory to sys.path
api_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "api"))
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

from app.main import app

async def run_benchmark():
    large_csv_path = os.path.join(os.path.dirname(__file__), "..", "sample-data", "large_test.csv")
    if not os.path.exists(large_csv_path):
        print(f"Error: {large_csv_path} not found. Run generate_large_csv.py first.")
        sys.exit(1)

    with open(large_csv_path, "rb") as f:
        content = f.read()

    row_count = len(content.decode("utf-8").splitlines()) - 1
    print(f"=== Benchmarking POST /ingest with {row_count:,} rows dataset ===")

    latencies = []
    iterations = 20

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for i in range(iterations):
            files = {"file": (f"benchmark_{i}.csv", content, "text/csv")}
            start = time.perf_counter()
            response = await client.post("/ingest", files=files)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            latencies.append(elapsed_ms)
            assert response.status_code == 202

    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95)]
    max_lat = max(latencies)
    min_lat = min(latencies)

    print("\n--- BENCHMARK RESULTS ---")
    print(f"Iterations:   {iterations}")
    print(f"Dataset Size: {row_count:,} rows ({len(content)/1024:.1f} KB)")
    print(f"Min Latency:  {min_lat:.2f} ms")
    print(f"p50 Latency:  {p50:.2f} ms")
    print(f"p95 Latency:  {p95:.2f} ms")
    print(f"Max Latency:  {max_lat:.2f} ms")
    print("-------------------------")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
