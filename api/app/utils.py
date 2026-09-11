import hashlib
import uuid
import re
from typing import Any

def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:16]

def generate_job_id() -> str:
    return uuid.uuid4().hex[:8]

def infer_type(val: str) -> str:
    if val is None or val == "":
        return "Unknown"
    val_str = str(val).strip()
    if val_str.lower() in ("true", "false", "yes", "no"):
        return "Boolean"
    try:
        int(val_str)
        if re.match(r'^(id|.*_id|code|zip|phone)$', val_str, re.IGNORECASE):
            return "ID-like"
        return "Integer"
    except ValueError:
        pass
    try:
        float(val_str)
        return "Float"
    except ValueError:
        pass
    if re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}', val_str):
        return "Date-like"
    return "Text"
