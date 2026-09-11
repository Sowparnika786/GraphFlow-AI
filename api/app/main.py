import os
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Optional, Dict, Any, List

from app.config import config
from app.models import IngestResponse, StatusResponse, HealthResponse, ChatRequest, ChatResponse, DatasetProfile
from app.kafka_service import kafka_service
from app.neo4j_service import neo4j_service
from app.csv_service import csv_service
from app.chat_service import chat_service
from app.utils import generate_job_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("graphflow-api")

app = FastAPI(
    title="GraphFlow AI API",
    description="Data In, Grounded Answers Out. CSV -> Kafka -> Neo4j -> Grounded Chatbot",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    logger.info("Initializing GraphFlow AI API...")
    neo4j_service.init_schema()

@app.get("/health", response_model=HealthResponse)
def get_health():
    kafka_ok = kafka_service.check_health()
    neo4j_ok = neo4j_service.check_health()
    overall_ok = kafka_ok and neo4j_ok
    return HealthResponse(
        status="ok" if overall_ok else "unhealthy",
        kafka_connected=kafka_ok,
        neo4j_connected=neo4j_ok
    )

@app.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_csv(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a valid CSV file.")

    content = await file.read()
    try:
        dataset_id, headers, rows = csv_service.parse_and_validate(content, file.filename)
    except Exception as e:
        logger.warning(f"CSV Ingestion validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    job_id = generate_job_id()
    rows_total = len(rows)

    try:
        neo4j_service.init_job(job_id=job_id, dataset_id=dataset_id, rows_total=rows_total)
    except Exception as e:
        logger.error(f"Failed to initialize job in Neo4j: {e}")
        raise HTTPException(status_code=500, detail="Failed to initialize ingestion job.")

    try:
        kafka_service.publish_rows(job_id=job_id, dataset_id=dataset_id, filename=file.filename, rows=rows)
    except Exception as e:
        logger.error(f"Failed to publish CSV rows to Kafka: {e}")
        raise HTTPException(status_code=500, detail="Kafka unavailable or publish failed.")

    return IngestResponse(
        job_id=job_id,
        rows_received=rows_total,
        status="queued"
    )

@app.get("/status", response_model=StatusResponse)
def get_status(job_id: str = Query(..., description="Job ID")):
    job_info = neo4j_service.get_job_status(job_id)
    if not job_info:
        raise HTTPException(status_code=404, detail=f"Job ID '{job_id}' not found.")

    rows_total = job_info.get("rows_total", 0)
    rows_loaded = job_info.get("rows_loaded", 0)
    rows_failed = job_info.get("rows_failed", 0)
    status_str = job_info.get("status", "queued")

    progress = 0.0
    if rows_total > 0:
        progress = round(((rows_loaded + rows_failed) / rows_total) * 100, 1)

    return StatusResponse(
        job_id=job_id,
        status=status_str,
        rows_total=rows_total,
        rows_loaded=rows_loaded,
        rows_failed=rows_failed,
        progress_percentage=progress
    )

@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    return chat_service.process_question(request.question)

@app.post("/profile", response_model=DatasetProfile)
async def profile_csv(file: UploadFile = File(...)):
    content = await file.read()
    dataset_id, headers, rows = csv_service.parse_and_validate(content, file.filename or "data.csv")
    profile = csv_service.generate_profile(dataset_id, file.filename or "data.csv", headers, rows)
    return profile

@app.get("/datasets/latest")
def get_latest_dataset():
    latest = neo4j_service.get_latest_dataset()
    if not latest:
        return {"has_dataset": False}
    return {"has_dataset": True, "dataset": latest}

@app.get("/graph/sample")
def get_graph_sample(limit: int = 30):
    query = """
    MATCH (d:Dataset)-[r:HAS_ROW]->(row:Row)
    RETURN d.id AS dataset_id, d.filename AS filename, row.row_index AS row_index, properties(row) AS properties
    LIMIT $limit
    """
    try:
        res = neo4j_service.execute_read_query(query, {"limit": limit})
        nodes = []
        links = []
        if res:
            ds_id = res[0].get("dataset_id", "ds1")
            ds_name = res[0].get("filename", "employees.csv")
            nodes.append({"id": f"dataset_{ds_id}", "label": ds_name, "type": "Dataset"})
            for idx, r in enumerate(res):
                row_idx = r.get("row_index", idx)
                row_id = f"row_{ds_id}_{row_idx}"
                props = r.get("properties") or r.get("r", {})
                nodes.append({"id": row_id, "label": f"Row #{row_idx}", "type": "Row", "props": props})
                links.append({"source": f"dataset_{ds_id}", "target": row_id, "label": "HAS_ROW"})
        return {"nodes": nodes, "links": links}
    except Exception as e:
        logger.warning(f"Failed to fetch graph sample: {e}")
        return {"nodes": [], "links": []}

# Mount UI static files
ui_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "ui", "src"))
if os.path.exists(ui_dir):
    app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")
