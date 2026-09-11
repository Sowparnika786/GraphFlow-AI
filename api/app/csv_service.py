import csv
import io
import logging
from typing import Dict, Any, List, Tuple
from app.utils import compute_sha256, infer_type
from app.models import DatasetProfile, ColumnProfile

logger = logging.getLogger(__name__)

class CSVService:
    def parse_and_validate(self, content: bytes, filename: str) -> Tuple[str, List[str], List[Dict[str, Any]]]:
        if not content or len(content.strip()) == 0:
            raise ValueError("Empty CSV file provided")

        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                text = content.decode('latin-1')
            except Exception as e:
                raise ValueError(f"Unable to decode file with UTF-8 or Latin-1: {e}")

        # Check for non-CSV / malformed binaries
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            raise ValueError("CSV contains zero non-empty lines")

        dataset_id = compute_sha256(content)
        
        # Use csv.DictReader
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("CSV header is missing or empty")

        headers = [h.strip() for h in reader.fieldnames if h and h.strip()]
        if not headers:
            raise ValueError("CSV contains no valid column headers")

        rows = []
        for idx, row in enumerate(reader):
            # Clean keys and values
            cleaned_row = {}
            for k, v in row.items():
                if k is not None:
                    clean_k = k.strip()
                    if clean_k:
                        cleaned_row[clean_k] = v.strip() if v is not None else ""
            rows.append(cleaned_row)

        return dataset_id, headers, rows

    def generate_profile(self, dataset_id: str, filename: str, headers: List[str], rows: List[Dict[str, Any]]) -> DatasetProfile:
        total_rows = len(rows)
        total_columns = len(headers)
        missing_values = 0

        columns_profile = []
        for h in headers:
            vals = [r.get(h, "") for r in rows]
            non_null_vals = [v for v in vals if v != ""]
            missing_values += (total_rows - len(non_null_vals))
            
            unique_count = len(set(vals))
            non_null_pct = round((len(non_null_vals) / total_rows * 100), 1) if total_rows > 0 else 0.0
            
            # Infer type from non-null sample
            sample_type = "Text"
            example_val = non_null_vals[0] if non_null_vals else None
            if non_null_vals:
                types = [infer_type(v) for v in non_null_vals[:20]]
                # Most common type in sample
                sample_type = max(set(types), key=types.count)

            columns_profile.append(ColumnProfile(
                name=h,
                detected_type=sample_type,
                non_null_pct=non_null_pct,
                unique_count=unique_count,
                example=example_val
            ))

        suggested = self.generate_suggested_questions(headers, rows)

        return DatasetProfile(
            dataset_id=dataset_id,
            filename=filename,
            total_rows=total_rows,
            total_columns=total_columns,
            missing_values=missing_values,
            columns=columns_profile,
            suggested_questions=suggested
        )

    def generate_suggested_questions(self, headers: List[str], rows: List[Dict[str, Any]]) -> List[str]:
        suggestions = ["How many rows are there?", "What columns are available?", "Show the first 5 rows."]
        
        # Categorize columns
        numeric_cols = []
        text_cols = []
        for h in headers:
            sample_vals = [r.get(h, "") for r in rows[:10] if r.get(h, "")]
            if sample_vals:
                t = infer_type(sample_vals[0])
                if t in ("Integer", "Float"):
                    numeric_cols.append(h)
                elif t in ("Text", "ID-like"):
                    text_cols.append(h)

        if text_cols:
            c = text_cols[0]
            suggestions.append(f"Count records by {c}")
            # Pick a sample value
            vals = [r.get(c, "") for r in rows if r.get(c, "")]
            if vals:
                sample_val = vals[0]
                suggestions.append(f"Show rows where {c} = {sample_val}")
                suggestions.append(f"Which {c} occurs most?")

        if numeric_cols:
            num_c = numeric_cols[0]
            suggestions.append(f"What is the average {num_c}?")

        return suggestions[:6]

csv_service = CSVService()
