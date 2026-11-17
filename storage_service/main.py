import os
import sys
import json
import time
import threading
from urllib.parse import urlparse, parse_qs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

PORT = int(os.environ.get("PORT", 8003))
COSMOS_ENDPOINT = os.environ.get("COSMOS_ENDPOINT")
COSMOS_KEY = os.environ.get("COSMOS_KEY")
DATABASE_NAME = os.environ.get("COSMOS_DATABASE", "SmartCityDB")
CONTAINER_NAME = os.environ.get("COSMOS_CONTAINER", "TelemetryReadings")

class DistributedStorageDriver:
    def __init__(self):
        self.lock = threading.Lock()
        self.is_cloud = False
        self.cosmos_client = None
        self.container = None
        self.local_partitions = {
            "central": [],
            "industrial": [],
            "residential": [],
            "waterfront": [],
            "suburban": []
        }
        self.write_count = 0
        self.read_count = 0

        if COSMOS_ENDPOINT and COSMOS_KEY:
            try:
                from azure.cosmos import CosmosClient, PartitionKey
                self.cosmos_client = CosmosClient(COSMOS_ENDPOINT, credential=COSMOS_KEY)
                db = self.cosmos_client.create_database_if_not_exists(id=DATABASE_NAME)
                self.container = db.create_container_if_not_exists(
                    id=CONTAINER_NAME,
                    partition_key=PartitionKey(path="/district_id")
                )
                self.is_cloud = True
                print(f"[StorageService] Connected to live Azure Cosmos DB at {COSMOS_ENDPOINT}")
            except Exception as e:
                print(f"[StorageService] Warning: Failed to connect to Azure Cosmos DB: {e}. Falling back to partitioned local driver.")
        else:
            print("[StorageService] Running in Local Partitioned Storage Mode (Azure Cosmos DB PartitionKey emulation: /district_id)")

    def save(self, reading: dict) -> dict:
        district = reading.get("district_id", "central").lower()
        with self.lock:
            self.write_count += 1
            if self.is_cloud and self.container:
                try:
                    self.container.upsert_item(reading)
                    return {"status": "SAVED_COSMOS_DB", "partition_key": district, "id": reading.get("id")}
                except Exception as e:
                    print(f"[StorageService] Cloud write error: {e}")

            if district not in self.local_partitions:
                self.local_partitions[district] = []
            
            if len(self.local_partitions[district]) > 5000:
                self.local_partitions[district].pop(0)
            self.local_partitions[district].append(reading)

            return {"status": "SAVED_LOCAL_PARTITION", "partition_key": district, "id": reading.get("id")}

    def query(self, district_id: str = None, limit: int = 50) -> list:
        with self.lock:
            self.read_count += 1
            if self.is_cloud and self.container and district_id:
                try:
                    query = f"SELECT TOP {limit} * FROM c WHERE c.district_id = @district ORDER BY c.timestamp DESC"
                    params = [{"name": "@district", "value": district_id.lower()}]
                    items = list(self.container.query_items(
                        query=query,
                        parameters=params,
                        partition_key=district_id.lower()
                    ))
                    return items
                except Exception as e:
                    print(f"[StorageService] Cloud query error: {e}")

            if district_id:
                partition = self.local_partitions.get(district_id.lower(), [])
                return list(reversed(partition))[:limit]
            else:
                combined = []
                for part in self.local_partitions.values():
                    combined.extend(part)
                combined.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
                return combined[:limit]

    def get_stats(self) -> dict:
        with self.lock:
            partitions_info = {}
            total_docs = 0
            for d, docs in self.local_partitions.items():
                count = len(docs)
                partitions_info[d] = {"document_count": count}
                total_docs += count

            return {
                "driver": "Azure Cosmos DB (SDK Connected)" if self.is_cloud else "Emulated Partitioned NoSQL (Cosmos DB Scheme)",
                "database": DATABASE_NAME,
                "container": CONTAINER_NAME,
                "partition_key_path": "/district_id",
                "total_documents_in_memory": total_docs,
                "total_write_ops": self.write_count,
                "total_read_ops": self.read_count,
                "partitions": partitions_info
            }

storage_driver = DistributedStorageDriver()

class StorageHTTPHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: dict):
        response_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._send_json(200, {"status": "UP", "cloud_sync": storage_driver.is_cloud})
        elif parsed.path == "/api/telemetry/stats":
            self._send_json(200, storage_driver.get_stats())
        elif parsed.path == "/api/telemetry/query":
            qs = parse_qs(parsed.query)
            district_id = qs.get("district_id", [None])[0]
            limit = int(qs.get("limit", [50])[0])
            results = storage_driver.query(district_id=district_id, limit=limit)
            self._send_json(200, {
                "count": len(results),
                "district_id": district_id,
                "items": results
            })
        elif parsed.path == "/metrics":
            self._send_json(200, {
                "service": "Storage-Service",
                "write_ops": storage_driver.write_count,
                "read_ops": storage_driver.read_count
            })
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/telemetry":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self._send_json(400, {"error": "Empty payload"})
                return

            raw_body = self.rfile.read(content_length)
            try:
                reading = json.loads(raw_body.decode("utf-8"))
            except Exception as e:
                self._send_json(400, {"error": f"Invalid JSON: {str(e)}"})
                return

            res = storage_driver.save(reading)
            self._send_json(201, res)
        else:
            self._send_json(404, {"error": "Endpoint Not Found"})

    def log_message(self, format, *args):
        return

def run_server():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), StorageHTTPHandler)
    print(f"[StorageService] Running on port {PORT}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[StorageService] Shutting down...")
        server.server_close()

if __name__ == "__main__":
    run_server()
