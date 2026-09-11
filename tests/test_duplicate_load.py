import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.neo4j_service import neo4j_service

@pytest.mark.asyncio
async def test_duplicate_upload_idempotency():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        csv_data = b"Name,Department,Salary,City\nArun,Sales,25000,Chennai\nPriya,Billing,30000,Coimbatore\n"
        files = {"file": ("employees.csv", csv_data, "text/csv")}

        # First Ingestion
        res1 = await client.post("/ingest", files=files)
        assert res1.status_code == 202
        
        # Get dataset_id from computation
        from app.utils import compute_sha256
        dataset_id = compute_sha256(csv_data)

        counts1 = neo4j_service.get_dataset_counts(dataset_id)
        assert counts1["dataset_nodes"] == 1
        assert counts1["row_nodes"] == 2

        # Second Ingestion (Exact same CSV file uploaded again)
        res2 = await client.post("/ingest", files={"file": ("employees.csv", csv_data, "text/csv")})
        assert res2.status_code == 202

        counts2 = neo4j_service.get_dataset_counts(dataset_id)
        assert counts2["dataset_nodes"] == 1
        assert counts2["row_nodes"] == 2  # Row count MUST NOT increase!
