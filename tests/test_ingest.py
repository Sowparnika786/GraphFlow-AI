import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_ingest_valid_csv():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        csv_data = b"Name,Department,Salary,City\nArun,Sales,25000,Chennai\nPriya,Billing,30000,Coimbatore\n"
        files = {"file": ("employees.csv", csv_data, "text/csv")}
        response = await client.post("/ingest", files=files)
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["rows_received"] == 2
        assert data["status"] == "queued"

@pytest.mark.asyncio
async def test_ingest_invalid_file_type():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("test.pdf", b"%PDF-1.4 dummy data", "application/pdf")}
        response = await client.post("/ingest", files=files)
        assert response.status_code == 400

@pytest.mark.asyncio
async def test_ingest_empty_csv():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("empty.csv", b"", "text/csv")}
        response = await client.post("/ingest", files=files)
        assert response.status_code == 400
