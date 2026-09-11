import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_chat_grounded_queries():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Ingest dataset with city, group, etc.
        csv_data = (
            b"customer_id,customer_name,group,order_id,order_amount,city,status\n"
            b"C001,Ravi Kumar,Billing,O1001,12500,Chennai,Completed\n"
            b"C002,Arun Raj,Support,O1002,8200,Bangalore,Open\n"
            b"C003,Kumar S,Billing,O1003,15300,Chennai,Completed\n"
            b"C004,Priya Nair,Sales,O1004,22100,Kochi,Completed\n"
        )
        await client.post("/ingest", files={"file": ("customers.csv", csv_data, "text/csv")})

        # Test 1: "give me the customers from the city Chennai" (From user's screenshot!)
        res1 = await client.post("/chat", json={"question": "give me the customers from the city Chennai"})
        assert res1.status_code == 200
        d1 = res1.json()
        assert d1["grounded"] is True
        assert d1["cypher"] is not None
        assert "2" in d1["answer"] or len(d1["result"]) == 2

        # Test 2: "How many rows are there?"
        res2 = await client.post("/chat", json={"question": "How many rows are there?"})
        assert res2.status_code == 200
        d2 = res2.json()
        assert d2["grounded"] is True

        # Test 3: "What columns are available?"
        res3 = await client.post("/chat", json={"question": "What columns are available?"})
        assert res3.status_code == 200
        d3 = res3.json()
        assert d3["grounded"] is True
        assert "customer_name" in d3["answer"] or "city" in d3["answer"]

        # Test 4: "What is Arun's blood group?" (Missing attribute check)
        res4 = await client.post("/chat", json={"question": "What is Arun's blood group?"})
        assert res4.status_code == 200
        d4 = res4.json()
        assert d4["grounded"] is False
        assert d4["cypher"] is None

        # Test 5: "What is Arun's order amount?" (Present attribute check)
        res5 = await client.post("/chat", json={"question": "What is Arun's order amount?"})
        assert res5.status_code == 200
        d5 = res5.json()
        assert d5["grounded"] is True
        assert "8200" in d5["answer"] or "Arun Raj" in d5["answer"]

        # Test 6: "What is Arun's salary?" (Missing column with existing entity)
        res6 = await client.post("/chat", json={"question": "What is Arun's salary?"})
        assert res6.status_code == 200
        d6 = res6.json()
        assert d6["grounded"] is False
        assert "Arun Raj" in d6["answer"] or "salary" in d6["answer"]

