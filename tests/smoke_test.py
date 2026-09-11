import sys
import time
import httpx

def run_smoke_test(base_url: str = "http://127.0.0.1:8000"):
    print(f"--- Running GraphFlow AI Smoke Test against {base_url} ---")
    
    # 1. Health check
    try:
        r = httpx.get(f"{base_url}/health", timeout=5.0)
        assert r.status_code == 200
        print("✓ Health Check Passed:", r.json())
    except Exception as e:
        print("✗ Health Check Failed:", e)
        sys.exit(1)

    # 2. Upload CSV
    csv_bytes = (
        b"Name,Department,Salary,City\n"
        b"Arun,Sales,25000,Chennai\n"
        b"Priya,Billing,30000,Coimbatore\n"
        b"Kumar,Sales,28000,Madurai\n"
        b"Meena,HR,32000,Chennai\n"
    )
    files = {"file": ("smoke_employees.csv", csv_bytes, "text/csv")}
    try:
        r = httpx.post(f"{base_url}/ingest", files=files, timeout=5.0)
        assert r.status_code == 202
        job_data = r.json()
        job_id = job_data["job_id"]
        print("✓ CSV Ingestion Queued. Job ID:", job_id)
    except Exception as e:
        print("✗ CSV Ingestion Failed:", e)
        sys.exit(1)

    # 3. Poll Status
    status_ok = False
    for _ in range(10):
        r = httpx.get(f"{base_url}/status?job_id={job_id}")
        if r.status_code == 200:
            st = r.json()
            print(f"  Status Poll: {st['status']} ({st['rows_loaded']}/{st['rows_total']})")
            if st["status"] == "complete":
                status_ok = True
                break
        time.sleep(0.5)

    if not status_ok:
        print("✗ Ingestion did not complete in time.")
        sys.exit(1)
    print("✓ Job Status Complete!")

    # 4. Test Chatbot
    chat_queries = [
        ("How many rows are there?", True),
        ("What columns are available?", True),
        ("How many rows have Department = Sales?", True),
        ("What is Arun's blood group?", False)
    ]

    for q, expected_grounded in chat_queries:
        r = httpx.post(f"{base_url}/chat", json={"question": q})
        assert r.status_code == 200
        res = r.json()
        assert res["grounded"] == expected_grounded
        print(f"✓ Question: '{q}' -> Grounded: {res['grounded']}, Answer: '{res['answer'][:60]}...'")

    print("\n==========================================")
    print("ALL SMOKE TESTS PASSED SUCCESSFULLY!")
    print("==========================================\n")

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    run_smoke_test(url)
