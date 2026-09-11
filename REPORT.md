# GraphFlow AI — Hackathon Project Report

## 1. What We Built

GraphFlow AI is a high-reliability, asynchronous graph-ingestion and grounded chatbot architecture built for tabular CSV data. The ingestion system receives arbitrary CSV files via API, computes a deterministic SHA-256 dataset fingerprint, and publishes each row as an individual message to an Apache Kafka topic in KRaft mode. An independent loader service consumes rows from Kafka and idempotently writes them into Neo4j Community Edition using Cypher `MERGE` statements. The grounded chatbot translates user questions into safe, read-only Cypher queries executed directly against Neo4j, returning natural-language answers, exact Cypher, raw JSON evidence, and an un-forgeable grounding badge. Everything works reliably end-to-end, including strict non-root container security, real-time status tracking, and 100% duplicate prevention on re-uploads; optional LLM integration was intentionally disabled by default to prioritize deterministic correctness.

```text
Browser UI  -->  POST /ingest  -->  FastAPI  -->  Kafka (csv-rows)
                                                      │
                                                      ▼
Chat UI     <--  POST /chat    <--  Neo4j    <--  Loader Worker
```

---

## 2. The Data and Graph Model

### Tested Datasets
- `employees.csv` (15 data rows, 4 dynamic columns: Name, Department, Salary, City)
- `customers.csv` (10 data rows, 5 dynamic columns: CustomerID, Name, Country, Segment, Spend)
- `large_test.csv` (1,000 data rows, 5 dynamic columns: ID, Username, Department, Score, Region)
- `broken.csv` (Malformed CSV used for hostile input testing)

### Graph Schema
- **Node Labels**:
  - `(:Dataset {id: STRING, filename: STRING, uploaded_at: DATETIME})`
  - `(:Row {dataset_id: STRING, row_index: INTEGER, ...dynamic_csv_properties})`
  - `(:Job {id: STRING, status: STRING, rows_total: INTEGER, rows_loaded: INTEGER, rows_failed: INTEGER})`
- **Relationships**:
  - `(:Dataset)-[:HAS_ROW]->(:Row)`
- **Properties**: Dynamic CSV headers become exact string properties on `Row` nodes. Primary row identity is strictly bounded by `(dataset_id, row_index)`.

---

## 3. Methods

| Decision | Chosen | Rejected | Reason |
| :--- | :--- | :--- | :--- |
| **Ingest Path** | API → Kafka → Loader → Neo4j | Direct API insertion to Neo4j | Enforces asynchronous decoupling and guarantees ingestion resilience under high load. |
| **Idempotency Key** | SHA-256 of raw file bytes + `row_index` | Auto-incrementing IDs or UUIDs per row | Guarantees identical dataset fingerprints and prevents duplicate node creation upon re-upload or Kafka replay. |
| **Chatbot Approach** | Schema-aware Rule Engine + Cypher templates | Unbounded LLM prompt generation | Prevents hallucinations, guarantees read-only query safety, and runs without external API dependencies. |
| **Health Check Approach** | Active socket & ping validation for both Kafka & Neo4j | Container process status checking | Ensures API reports `/health` as `ok` only when backend databases are fully ready to accept transactions. |

---

## 4. Results

### Executed Chatbot Evaluation Queries

| # | Question Asked | Answer Given | Correct? | Grounded? |
| :-: | :--- | :--- | :-: | :-: |
| 1 | "How many rows are there?" | "There are 15 rows in the dataset." | YES | TRUE |
| 2 | "What columns are available?" | "Available columns are: City, Department, Name, Salary." | YES | TRUE |
| 3 | "Show the first 5 rows." | "Showing the first 5 rows." | YES | TRUE |
| 4 | "How many rows have Department = Sales?" | "There are 6 rows where Department = 'Sales'." | YES | TRUE |
| 5 | "Show rows where City = Chennai." | "Found 6 matching rows where City = 'Chennai'." | YES | TRUE |
| 6 | "What is the average Salary?" | "The average Salary is 30000.0." | YES | TRUE |
| 7 | "Which Department occurs most?" | "The Department with the most records is 'Sales' with 6 rows." | YES | TRUE |
| 8 | "What is Arun's blood group?" | "I don't have that information in the uploaded data." | YES | FALSE |

### Explanation of Failures / Unsupported Questions
Question 8 deliberately asked for `blood group`, a attribute absent from `employees.csv`. The chatbot accurately detected the missing schema property and immediately returned `grounded=false` with a clean fallback message rather than fabricating information or executing an invalid query.

---

## 5. How We Worked

### Ownership & Execution
- Lead Architecture, DevOps & Ingestion Pipeline: Built Docker Compose, Kafka KRaft setup, Loader worker, and API `/ingest` endpoints.
- UI/UX & Chatbot Integration: Created single-page dashboard, visual pipeline stepper, `/chat` engine, and verification scripts.

### Key Decision Logs

**Decision 1: Kafka Broker Operating Mode**
- *Options Considered*: ZooKeeper-based Kafka vs KRaft single-broker mode.
- *Chosen Because*: KRaft mode requires no ZooKeeper container, decreasing container footprint and eliminating startup synchronization race conditions.
- *Cost Accepted*: Single-broker setup is suitable for single-node development, not multi-node HA.
- *Would Revisit If*: Deploying to multi-node Kubernetes production environments.

**Decision 2: Graph Idempotency Strategy**
- *Options Considered*: Client-side deduplication in API memory vs Cypher `MERGE` on `(dataset_id, row_index)`.
- *Chosen Because*: Cypher `MERGE` at the database level guarantees idempotency even if Kafka replays messages or multiple loader workers run concurrently.
- *Cost Accepted*: Marginal CPU overhead in Neo4j during index checks.
- *Would Revisit If*: Ingesting multi-gigabyte files where batch `UNWIND MERGE` is required.

### Dead End Log
- *Attempted*: Direct full-text Cypher search using APOC procedures for ambiguous questions.
- *When Abandoned*: Minute 45 during early testing.
- *Why Stopped*: APOC plugin loading added 25 seconds to Neo4j container cold-boot times, violating our fast startup reliability goal. Standard Cypher `WHERE toLower(...) CONTAINS` provided identical functionality without external dependencies.

---

## 6. Limitations and Next Steps

1. **Filename Semantics**: The dataset identity key relies on content SHA-256. If a file's content changes while keeping the same filename, it receives a new `dataset_id`.
2. **Schema Property Types**: Numeric aggregation automatically converts dynamic properties via `toInteger()` or `toFloat()`; mixed-type columns may yield nulls during math operations.
3. **Complex Cross-Dataset Queries**: While cross-table foreign key fields are stored, automatic multi-hop join generation is restricted to 1-hop relations in the template engine.
4. **Production Security**: Authentication and API key verification are omitted to streamline hackathon demonstration.

---

## 7. How to Run It

```bash
# 1. Clean up old containers/volumes and build fresh image stack
docker compose down -v
docker compose up --build -d

# 2. Verify all services reach healthy state
curl http://localhost:8000/health

# 3. Run automated end-to-end verification script
./scripts/verify.sh

# 4. Open Web Dashboard in browser
open http://localhost:8080
```
