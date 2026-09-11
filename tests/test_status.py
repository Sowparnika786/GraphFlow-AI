import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_status_workflow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Ingest CSV first
        csv_data = b"Name,Department,Salary,City\nArun,Sales,25000,Chennai\nPriya,Billing,30000,Coimbatore\n"
        files = {"file": ("employees.csv", csv_data, "text/csv")}
        ingest_res = await client.post("/ingest", files=files)
        assert ingest_res.status_code == 202
        job_id = ingest_res.json()["job_id"]

        # Poll status
        status_res = await client.get(f"/status?job_id={job_id}")
        assert status_res.status_code == 200
        data = status_res.json()
        assert data["job_id"] == job_id
        assert data["rows_total"] == 2
        assert data["rows_loaded"] >= 0
        assert data["status"] in ("queued", "loading", "complete")

@pytest.mark.asyncio
async def test_status_nonexistent_job():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/status?job_id=nonexistent_12345")
        assert res.status_code == 404
