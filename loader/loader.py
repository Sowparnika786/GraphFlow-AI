import os
import json
import time
import logging
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable
from neo4j import GraphDatabase, Driver

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("graphflow-loader")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "csvgraphdb")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "csv-rows")

def get_neo4j_driver() -> Driver:
    while True:
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            driver.verify_connectivity()
            logger.info("Connected successfully to Neo4j.")
            return driver
        except Exception as e:
            logger.warning(f"Waiting for Neo4j... ({e})")
            time.sleep(3)

def get_kafka_consumer() -> KafkaConsumer:
    while True:
        try:
            consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id="graphflow-loader-group",
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                value_deserializer=lambda v: json.loads(v.decode('utf-8'))
            )
            logger.info(f"Connected successfully to Kafka. Consuming topic '{KAFKA_TOPIC}'.")
            return consumer
        except Exception as e:
            logger.warning(f"Waiting for Kafka broker... ({e})")
            time.sleep(3)

def process_message(driver: Driver, msg: dict):
    job_id = msg.get("job_id")
    dataset_id = msg.get("dataset_id")
    filename = msg.get("filename")
    row_index = msg.get("row_index")
    row_data = msg.get("row_data", {})
    rows_total = msg.get("rows_total", 1)

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
        session.run(
            cypher,
            {
                "dataset_id": dataset_id,
                "filename": filename,
                "row_index": row_index,
                "row_data": row_data,
                "job_id": job_id,
                "rows_total": rows_total
            }
        )

def process_failure(driver: Driver, job_id: str, rows_total: int):
    cypher = """
    MATCH (j:Job {id: $job_id})
    SET j.rows_failed = coalesce(j.rows_failed, 0) + 1,
        j.status = CASE WHEN (coalesce(j.rows_loaded, 0) + coalesce(j.rows_failed, 0) + 1) >= $rows_total THEN 'complete' ELSE 'loading' END
    """
    try:
        with driver.session() as session:
            session.run(cypher, {"job_id": job_id, "rows_total": rows_total})
    except Exception as e:
        logger.error(f"Failed to record row failure for job {job_id}: {e}")

def main():
    logger.info("Starting GraphFlow AI Loader Worker...")
    neo4j_driver = get_neo4j_driver()
    kafka_consumer = get_kafka_consumer()

    for message in kafka_consumer:
        try:
            payload = message.value
            process_message(neo4j_driver, payload)
        except Exception as e:
            logger.error(f"Error processing Kafka message offset {message.offset}: {e}")
            if isinstance(message.value, dict) and "job_id" in message.value:
                process_failure(neo4j_driver, message.value["job_id"], message.value.get("rows_total", 1))

if __name__ == "__main__":
    main()
