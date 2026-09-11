from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field

class IngestResponse(BaseModel):
    job_id: str
    rows_received: int
    status: str = "queued"

class StatusResponse(BaseModel):
    job_id: str
    status: str  # queued, loading, complete, failed
    rows_total: int
    rows_loaded: int
    rows_failed: int
    progress_percentage: Optional[float] = None

class HealthResponse(BaseModel):
    status: str  # ok or unhealthy
    kafka_connected: bool
    neo4j_connected: bool

class ChatRequest(BaseModel):
    question: str

class ChatResponse(BaseModel):
    answer: str
    cypher: Optional[str] = None
    result: List[Any] = []
    grounded: bool

class ColumnProfile(BaseModel):
    name: str
    detected_type: str
    non_null_pct: float
    unique_count: int
    example: Optional[Any] = None

class DatasetProfile(BaseModel):
    dataset_id: str
    filename: str
    total_rows: int
    total_columns: int
    missing_values: int
    columns: List[ColumnProfile]
    suggested_questions: List[str]
