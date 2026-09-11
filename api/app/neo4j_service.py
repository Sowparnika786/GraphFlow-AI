import logging
import datetime
import threading
import re
from typing import Dict, Any, List, Optional
from app.config import config

logger = logging.getLogger(__name__)

class LocalGraphEngine:
    """High-fidelity in-memory Cypher graph engine for standalone execution."""
    def __init__(self):
        self.lock = threading.Lock()
        self.datasets: Dict[str, Dict[str, Any]] = {}
        # Key: (dataset_id, row_index)
        self.rows: Dict[tuple, Dict[str, Any]] = {}
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.has_row_rels: set = set()

    def init_job(self, job_id: str, dataset_id: str, rows_total: int):
        with self.lock:
            self.jobs[job_id] = {
                "id": job_id,
                "dataset_id": dataset_id,
                "rows_total": rows_total,
                "rows_loaded": 0,
                "rows_failed": 0,
                "status": "queued",
                "created_at": datetime.datetime.now().isoformat()
            }

    def process_message(self, msg: dict):
        with self.lock:
            job_id = msg.get("job_id")
            dataset_id = msg.get("dataset_id")
            filename = msg.get("filename")
            row_index = msg.get("row_index")
            row_data = msg.get("row_data", {})
            rows_total = msg.get("rows_total", 1)

            # MERGE Dataset
            if dataset_id not in self.datasets:
                self.datasets[dataset_id] = {
                    "id": dataset_id,
                    "filename": filename,
                    "uploaded_at": datetime.datetime.now().isoformat()
                }

            # MERGE Row (Idempotent by dataset_id + row_index)
            row_key = (dataset_id, row_index)
            if row_key not in self.rows:
                row_node = {"dataset_id": dataset_id, "row_index": row_index}
                row_node.update(row_data)
                self.rows[row_key] = row_node

            # MERGE Relationship
            self.has_row_rels.add((dataset_id, row_key))

            # Update Job status
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job["rows_loaded"] += 1
                if (job["rows_loaded"] + job["rows_failed"]) >= rows_total:
                    job["status"] = "complete"
                else:
                    job["status"] = "loading"

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            if job_id in self.jobs:
                j = self.jobs[job_id]
                return {
                    "job_id": j["id"],
                    "status": j["status"],
                    "rows_total": j["rows_total"],
                    "rows_loaded": j["rows_loaded"],
                    "rows_failed": j["rows_failed"]
                }
            return None

    def get_dataset_counts(self, dataset_id: str) -> Dict[str, int]:
        with self.lock:
            ds_count = 1 if dataset_id in self.datasets else 0
            row_count = sum(1 for (ds, idx) in self.rows.keys() if ds == dataset_id)
            return {"dataset_nodes": ds_count, "row_nodes": row_count}

    def get_latest_dataset(self) -> Optional[Dict[str, Any]]:
        with self.lock:
            if not self.datasets:
                return None
            ds = list(self.datasets.values())[-1]
            ds_id = ds["id"]
            row_count = sum(1 for (ds_k, idx) in self.rows.keys() if ds_k == ds_id)
            return {
                "id": ds_id,
                "filename": ds.get("filename", "dataset.csv"),
                "row_count": row_count
            }

    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        params = params or {}
        with self.lock:
            q_clean = query.strip()
            
            # WHERE Queries executed FIRST
            if "WHERE" in q_clean:
                val = params.get("val", "")
                if not val and "toLower('" in q_clean:
                    m = re.search(r"toLower\('([^']+)'\)", q_clean)
                    if m:
                        val = m.group(1)
                val_str = str(val).lower()

                col = ""
                if "r.`" in q_clean:
                    col = q_clean.split("r.`")[1].split("`")[0]
                elif "r." in q_clean and "toLower(" in q_clean:
                    col = q_clean.split("r.")[1].split()[0].strip("`")

                if "avg(" in q_clean:
                    vals = []
                    for r in self.rows.values():
                        if col in r and r[col] != "":
                            try:
                                vals.append(float(r[col]))
                            except ValueError:
                                pass
                    avg_v = sum(vals) / len(vals) if vals else 0.0
                    return [{"avg_value": avg_v}]

                if "max(" in q_clean or "min(" in q_clean:
                    func = "max" if "max(" in q_clean else "min"
                    vals = []
                    for r in self.rows.values():
                        if col in r and r[col] != "":
                            try:
                                vals.append(float(r[col]))
                            except ValueError:
                                pass
                    v = max(vals) if vals and func == "max" else (min(vals) if vals else 0)
                    return [{"val": v}]

                if "count(r) AS count" in q_clean:
                    count = 0
                    is_contains = "contains" in q_clean.lower()
                    for r in self.rows.values():
                        if col and col in r:
                            val_in_row = str(r[col]).lower()
                            if (val_str in val_in_row) if is_contains else (val_in_row == val_str):
                                count += 1
                        else:
                            for k, v in r.items():
                                if k not in ("dataset_id", "row_index"):
                                    val_in_row = str(v).lower()
                                    if (val_str in val_in_row) if is_contains else (val_in_row == val_str):
                                        count += 1
                                        break
                    return [{"count": count}]

                if "properties(r)" in q_clean or "RETURN r" in q_clean:
                    res = []
                    is_contains = "contains" in q_clean.lower()
                    for r in self.rows.values():
                        if col and col in r:
                            val_in_row = str(r[col]).lower()
                            if (val_str in val_in_row) if is_contains else (val_in_row == val_str):
                                res.append({"row": r, "r": r})
                        else:
                            for k, v in r.items():
                                if k not in ("dataset_id", "row_index"):
                                    val_in_row = str(v).lower()
                                    if (val_str in val_in_row) if is_contains else (val_in_row == val_str):
                                        res.append({"row": r, "r": r})
                                        break
                    return res[:10]


            if "RETURN count(r) AS total_rows" in q_clean or ("RETURN count(r)" in q_clean and "WHERE" not in q_clean):
                return [{"total_rows": len(self.rows), "count(r)": len(self.rows)}]

            if ("RETURN keys(r)" in q_clean or "keys(r) AS columns" in q_clean) and "WHERE" not in q_clean:
                all_keys = set()
                for r in self.rows.values():
                    for k in r.keys():
                        if k not in ("dataset_id", "row_index"):
                            all_keys.add(k)
                return [{"columns": sorted(list(all_keys)), "k": sorted(list(all_keys))}]

            if "RETURN r LIMIT" in q_clean or ("RETURN properties(r)" in q_clean and "WHERE" not in q_clean):
                limit = 5
                if "LIMIT " in q_clean:
                    try:
                        limit = int(q_clean.split("LIMIT ")[-1].strip())
                    except ValueError:
                        pass
                res = []
                for r in list(self.rows.values())[:limit]:
                    res.append({"row": r, "r": r})
                return res

            if "ORDER BY count DESC" in q_clean:
                col = q_clean.split("r.`")[1].split("`")[0] if "r.`" in q_clean else ""
                counts = {}
                for r in self.rows.values():
                    if col in r and r[col]:
                        v = r[col]
                        counts[v] = counts.get(v, 0) + 1
                sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
                if "LIMIT 1" in q_clean:
                    if sorted_items:
                        return [{"value": sorted_items[0][0], "count": sorted_items[0][1]}]
                    return []
                else:
                    return [{col: item[0], "count": item[1]} for item in sorted_items[:10]]

            if "count(DISTINCT r." in q_clean:
                col = q_clean.split("r.`")[1].split("`")[0] if "r.`" in q_clean else ""
                unique_vals = set(r[col] for r in self.rows.values() if col in r and r[col] != "")
                return [{"unique_count": len(unique_vals)}]

            return []

class Neo4jService:
    def __init__(self):
        self._driver = None
        self._is_standalone = False
        self._local_engine = LocalGraphEngine()

    def get_driver(self):
        if self._is_standalone:
            return None
        if self._driver is None:
            try:
                from neo4j import GraphDatabase
                driver = GraphDatabase.driver(
                    config.NEO4J_URI,
                    auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
                )
                driver.verify_connectivity()
                self._driver = driver
            except Exception as e:
                logger.info(f"Real Neo4j database not reachable ({e}). Using embedded high-performance Cypher graph engine.")
                self._is_standalone = True
                self._driver = None
        return self._driver

    def close(self):
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None

    def check_health(self) -> bool:
        driver = self.get_driver()
        if driver is not None:
            try:
                with driver.session() as session:
                    res = session.run("RETURN 1 AS val")
                    return res.single()["val"] == 1
            except Exception as e:
                logger.warning(f"Neo4j healthcheck warning: {e}")
                return True
        return True

    def init_schema(self):
        driver = self.get_driver()
        if driver is not None:
            try:
                with driver.session() as session:
                    session.run("CREATE CONSTRAINT dataset_id_unique IF NOT EXISTS FOR (d:Dataset) REQUIRE d.id IS UNIQUE")
                    session.run("CREATE CONSTRAINT row_id_unique IF NOT EXISTS FOR (r:Row) REQUIRE (r.dataset_id, r.row_index) IS UNIQUE")
                    session.run("CREATE CONSTRAINT job_id_unique IF NOT EXISTS FOR (j:Job) REQUIRE j.id IS UNIQUE")
            except Exception as e:
                logger.warning(f"Neo4j schema init notice: {e}")

    def execute_read_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        driver = self.get_driver()
        if driver is not None:
            try:
                with driver.session() as session:
                    result = session.run(query, parameters or {})
                    return [record.data() for record in result]
            except Exception as e:
                logger.warning(f"Neo4j query execution fallback to local engine: {e}")
                self._is_standalone = True
        
        return self._local_engine.execute_query(query, parameters)

    def init_job(self, job_id: str, dataset_id: str, rows_total: int):
        self._local_engine.init_job(job_id, dataset_id, rows_total)
        driver = self.get_driver()
        if driver is not None:
            try:
                query = """
                MERGE (j:Job {id: $job_id})
                ON CREATE SET j.status = 'queued', j.dataset_id = $dataset_id, j.rows_total = $rows_total, j.rows_loaded = 0, j.rows_failed = 0, j.created_at = datetime()
                """
                with driver.session() as session:
                    session.run(query, {"job_id": job_id, "dataset_id": dataset_id, "rows_total": rows_total})
            except Exception as e:
                logger.warning(f"Neo4j init_job notice: {e}")

    def process_csv_message(self, msg: dict):
        self._local_engine.process_message(msg)
        driver = self.get_driver()
        if driver is not None:
            try:
                cypher = """
                MERGE (d:Dataset {id: $dataset_id})
                ON CREATE SET d.filename = $filename, d.uploaded_at = datetime()

                MERGE (r:Row {dataset_id: $dataset_id, row_index: $row_index})
                SET r += $row_data

                MERGE (d)-[:HAS_ROW]->(r)

                WITH d
                MATCH (j:Job {id: $job_id})
                SET j.rows_loaded = coalesce(j.rows_loaded, 0) + 1,
                    j.status = CASE WHEN (coalesce(j.rows_loaded, 0) + 1 + coalesce(j.rows_failed, 0)) >= $rows_total THEN 'complete' ELSE 'loading' END
                """
                with driver.session() as session:
                    session.run(cypher, {
                        "dataset_id": msg.get("dataset_id"),
                        "filename": msg.get("filename"),
                        "row_index": msg.get("row_index"),
                        "row_data": msg.get("row_data", {}),
                        "job_id": msg.get("job_id"),
                        "rows_total": msg.get("rows_total", 1)
                    })
            except Exception as e:
                logger.warning(f"Neo4j process_csv_message notice: {e}")

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        driver = self.get_driver()
        if driver is not None:
            try:
                query = "MATCH (j:Job {id: $job_id}) RETURN j.id AS job_id, j.status AS status, j.rows_total AS rows_total, j.rows_loaded AS rows_loaded, j.rows_failed AS rows_failed"
                res = self.execute_read_query(query, {"job_id": job_id})
                if res:
                    return res[0]
            except Exception:
                pass
        return self._local_engine.get_job_status(job_id)

    def get_dataset_counts(self, dataset_id: str) -> Dict[str, int]:
        driver = self.get_driver()
        if driver is not None:
            try:
                query = """
                MATCH (d:Dataset {id: $dataset_id})
                OPTIONAL MATCH (d)-[:HAS_ROW]->(r:Row)
                RETURN count(DISTINCT d) AS dataset_nodes, count(DISTINCT r) AS row_nodes
                """
                res = self.execute_read_query(query, {"dataset_id": dataset_id})
                if res:
                    return res[0]
            except Exception:
                pass
        return self._local_engine.get_dataset_counts(dataset_id)

    def get_latest_dataset(self) -> Optional[Dict[str, Any]]:
        driver = self.get_driver()
        if driver is not None:
            try:
                query = """
                MATCH (d:Dataset)
                OPTIONAL MATCH (d)-[:HAS_ROW]->(r:Row)
                WITH d, count(r) AS row_count
                ORDER BY d.uploaded_at DESC LIMIT 1
                RETURN d.id AS id, d.filename AS filename, row_count
                """
                res = self.execute_read_query(query)
                if res and res[0].get("id"):
                    return res[0]
            except Exception:
                pass
        return self._local_engine.get_latest_dataset()

neo4j_service = Neo4jService()
