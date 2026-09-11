# GraphFlow AI

> **Data In. Grounded Answers Out.**

GraphFlow AI is a high-reliability, production-grade CSV ingestion pipeline and grounded graph database chatbot system. Every row of incoming tabular data streams through an asynchronous Kafka queue into Neo4j as an immutable graph dataset, allowing natural language queries to be dynamically translated into safe, read-only Cypher queries with 100% verifiable grounding.

---

## 🏗️ System Architecture

```text
 Browser / Client
       │
       ├── POST /ingest
       ├── GET  /status
       ├── GET  /health
       └── POST /chat
              │
              ▼
            API (FastAPI)
              │
              │ PRODUCED TO KAFKA
              ▼
         Apache Kafka (KRaft Mode)
       Topic: csv-rows
              │
              │ CONSUMED BY LOADER
              ▼
         Loader Worker Service
              │
              │ MERGE via Bolt Driver
              ▼
         Neo4j Graph Database
       (:Dataset)-[:HAS_ROW]->(:Row)
              ▲
              │ READ ONLY QUERY FOR CHAT
              │
         Grounded Chatbot Engine
```

---

## 🚀 Key Features

1. **Strict Async Pipeline**: CSV rows are published to Kafka topic `csv-rows` before reaching Neo4j via an isolated loader worker.
2. **Idempotent Storage (`MERGE`)**: Re-uploading the exact same CSV produces deterministic `dataset_id` (SHA-256) and zero duplicate nodes or relationships.
3. **Truthful `/health` & Real `/status`**: `/health` returns status `ok` only when BOTH Kafka and Neo4j are connected. `/status` provides real-time progress counters.
4. **Grounded Template Chatbot**: Rule-based intent engine mapping questions to dynamic Cypher queries. Returns `grounded=false` whenever data or schema is missing.
5. **Cypher Injection Shield**: Strictly enforces READ-ONLY Cypher queries (`MATCH`, `WHERE`, `RETURN`). Rejects `CREATE`, `MERGE`, `DELETE`, `DROP`, or procedure calls.
6. **Premium UI Dashboard**: Dark-theme enterprise dashboard with visual pipeline stepper, live progress bar, dataset profiling, and interactive chat.

---

## 🛠️ Technology Stack

- **Backend API**: Python 3.11, FastAPI, Pydantic v2
- **Message Broker**: Apache Kafka 3.7.0 (Single-broker, KRaft mode, No ZooKeeper)
- **Graph Database**: Neo4j 5.24 Community (`neo4j:5.24-community`)
- **Loader Worker**: Python 3.11 consumer using `kafka-python-ng` & official `neo4j` Bolt driver
- **Frontend UI**: Responsive HTML5 / CSS3 / Vanilla JS served via Nginx (non-root)
- **Containerization**: Docker Compose v2, pinned image tags, non-root container security

---

## ⚡ Quick Start

```bash
# 1. Clone repository and navigate to project directory
cd graphflow-ai

# 2. Start all services using Docker Compose
docker compose up --build -d

# 3. Verify health status
curl http://localhost:8000/health

# 4. Run automated test and verification suite
chmod +x scripts/verify.sh
./scripts/verify.sh
```

Access Points:
- **Web Dashboard**: [http://localhost:8080](http://localhost:8080)
- **FastAPI Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Neo4j Browser**: [http://localhost:7474](http://localhost:7474) (Credentials: `neo4j` / `csvgraphdb`)

---

## 📡 API Endpoint Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Returns status of Kafka and Neo4j connectivity |
| `POST` | `/ingest` | Accepts multipart CSV upload, queues rows to Kafka, returns `job_id` |
| `GET` | `/status` | Returns progress counters (`rows_loaded`, `rows_failed`, `rows_total`, `status`) |
| `POST` | `/chat` | Grounded chatbot query execution returning answer, Cypher, and raw Neo4j JSON |

---

## 🔒 Security & Reliability Guarantee

- Containers run as unprivileged non-root users (`appuser` / uid 10001).
- Neo4j password supplied strictly via environment variable (`NEO4J_PASSWORD`).
- Zero hardcoded credentials in application source code.
