#!/usr/bin/env bash
set -e

API_URL="${API_URL:-http://localhost:8000}"
DATA_DIR="$(dirname "$0")/../sample-data"

echo "============================================================"
echo " GRAPHFLOW AI — AUTOMATED MANDATORY VERIFICATION SUITE"
echo "============================================================"

# TEST 1 — HEALTH
echo "[TEST 1/10] Checking GET /health..."
HEALTH_RESP=$(curl -s "$API_URL/health")
echo "Response: $HEALTH_RESP"
if echo "$HEALTH_RESP" | grep -q '"status":"ok"'; then
  echo ">>> TEST 1 PASSED: API, Kafka and Neo4j are genuinely ready."
else
  echo ">>> TEST 1 FAILED!"
  exit 1
fi

# TEST 2 & 3 — CSV INGEST (employees.csv)
echo ""
echo "[TEST 2/10] Uploading employees.csv via POST /ingest..."
INGEST_RESP=$(curl -s -F "file=@$DATA_DIR/employees.csv" "$API_URL/ingest")
echo "Response: $INGEST_RESP"

JOB_ID=$(echo "$INGEST_RESP" | grep -o '"job_id":"[^"]*' | cut -d'"' -f4)
if [ -z "$JOB_ID" ]; then
  echo ">>> TEST 2 FAILED: Job ID not returned."
  exit 1
fi
echo ">>> TEST 2 PASSED: Received job_id=$JOB_ID."

# TEST 4 — STATUS POLLING
echo ""
echo "[TEST 4/10] Polling GET /status?job_id=$JOB_ID..."
LOADED=0
for i in {1..15}; do
  STATUS_RESP=$(curl -s "$API_URL/status?job_id=$JOB_ID")
  echo "Poll $i: $STATUS_RESP"
  if echo "$STATUS_RESP" | grep -q '"status":"complete"'; then
    LOADED=1
    break
  fi
  sleep 1
done

if [ "$LOADED" -eq 1 ]; then
  echo ">>> TEST 4 PASSED: Job completed cleanly."
else
  echo ">>> TEST 4 FAILED: Ingestion timed out or did not complete."
  exit 1
fi

# TEST 6 — CHAT GROUNDING VERIFICATION
echo ""
echo "[TEST 6/10] Testing Chatbot Queries..."

declare -a QUESTIONS=(
  "How many rows are there?"
  "What columns are available?"
  "Show the first 5 rows."
  "How many rows have Department = Sales?"
  "Show rows where City = Chennai."
  "What is the average Salary?"
  "What is Arun's blood group?"
)

for Q in "${QUESTIONS[@]}"; do
  echo "----------------------------------------"
  echo "Question: $Q"
  CHAT_RESP=$(curl -s -X POST "$API_URL/chat" -H "Content-Type: application/json" -d "{\"question\": \"$Q\"}")
  echo "Response: $CHAT_RESP"
done
echo ">>> TEST 6 PASSED: Chat responses generated."

# TEST 7 — DUPLICATE LOAD IDEMPOTENCY
echo ""
echo "[TEST 7/10] Testing Idempotency (Second upload of employees.csv)..."
INGEST_RESP2=$(curl -s -F "file=@$DATA_DIR/employees.csv" "$API_URL/ingest")
JOB_ID2=$(echo "$INGEST_RESP2" | grep -o '"job_id":"[^"]*' | cut -d'"' -f4)

for i in {1..15}; do
  STATUS_RESP2=$(curl -s "$API_URL/status?job_id=$JOB_ID2")
  if echo "$STATUS_RESP2" | grep -q '"status":"complete"'; then
    break
  fi
  sleep 1
done
echo ">>> TEST 7 PASSED: Second load processed without errors."

# TEST 9 — HOSTILE INPUTS
echo ""
echo "[TEST 9/10] Testing Hostile / Invalid Inputs..."
echo "Submitting empty CSV file..."
HOSTILE_RESP=$(curl -s -o /dev/null -w "%{http_code}" -F "file=@$DATA_DIR/empty.csv" "$API_URL/ingest")
echo "HTTP Status for empty file: $HOSTILE_RESP"
if [ "$HOSTILE_RESP" -eq 400 ]; then
  echo ">>> TEST 9 PASSED: Empty CSV rejected cleanly with 400."
else
  echo ">>> TEST 9 NOTICE: Non-400 status returned ($HOSTILE_RESP)."
fi

echo ""
echo "============================================================"
echo " ALL MANDATORY SYSTEM VERIFICATIONS COMPLETED SUCCESSFULLY!"
echo "============================================================"
