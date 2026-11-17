import os
import sys
import json
import time
import queue
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from common.models import SensorReading

PORT = int(os.environ.get("PORT", 8001))
PROCESSING_SERVICE_URL = os.environ.get("PROCESSING_SERVICE_URL", "http://127.0.0.1:8002/api/events")
STORAGE_SERVICE_URL = os.environ.get("STORAGE_SERVICE_URL", "http://127.0.0.1:8003/api/telemetry")

class Metrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.start_time = time.time()
        self.total_received = 0
        self.total_forwarded = 0
        self.validation_errors = 0
        self.network_errors = 0
        self.total_latency_ms = 0.0

    def record_success(self, latency_ms: float):
        with self.lock:
            self.total_received += 1
            self.total_latency_ms += latency_ms

    def record_error(self, is_validation: bool = False):
        with self.lock:
            if is_validation:
                self.validation_errors += 1
            else:
                self.network_errors += 1

    def get_stats(self):
        with self.lock:
            uptime = time.time() - self.start_time
            avg_lat = (self.total_latency_ms / self.total_received) if self.total_received > 0 else 0.0
            rps = (self.total_received / uptime) if uptime > 0 else 0.0
            return {
                "service": "IoT-Ingestion-Service",
                "uptime_seconds": round(uptime, 2),
                "total_received": self.total_received,
                "total_forwarded": self.total_forwarded,
                "validation_errors": self.validation_errors,
                "network_errors": self.network_errors,
                "avg_ingestion_latency_ms": round(avg_lat, 2),
                "current_throughput_rps": round(rps, 2)
            }

metrics = Metrics()
dispatch_queue = queue.Queue(maxsize=100000)

def forward_worker():
    while True:
        reading_dict = dispatch_queue.get()
        if reading_dict is None:
            break
        payload_bytes = json.dumps(reading_dict).encode("utf-8")
        
        try:
            req = urllib.request.Request(
                PROCESSING_SERVICE_URL,
                data=payload_bytes,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                pass
        except Exception:
            metrics.record_error(is_validation=False)

        try:
            req = urllib.request.Request(
                STORAGE_SERVICE_URL,
                data=payload_bytes,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                pass
        except Exception:
            metrics.record_error(is_validation=False)

        with metrics.lock:
            metrics.total_forwarded += 1
        dispatch_queue.task_done()

NUM_WORKERS = int(os.environ.get("FORWARD_WORKERS", 4))
workers = []
for _ in range(NUM_WORKERS):
    t = threading.Thread(target=forward_worker, daemon=True)
    t.start()
    workers.append(t)

class IngestionHTTPHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: dict):
        response_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/healthz":
            self._send_json(200, {"status": "UP", "queue_size": dispatch_queue.qsize()})
        elif self.path == "/metrics":
            self._send_json(200, metrics.get_stats())
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        start_t = time.time()
        if self.path in ("/api/telemetry", "/api/telemetry/batch"):
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self._send_json(400, {"error": "Empty payload"})
                metrics.record_error(is_validation=True)
                return

            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception as e:
                self._send_json(400, {"error": f"Invalid JSON: {str(e)}"})
                metrics.record_error(is_validation=True)
                return

            items = payload if isinstance(payload, list) else [payload]
            accepted = 0
            for item in items:
                is_valid, err_msg = SensorReading.validate(item)
                if not is_valid:
                    metrics.record_error(is_validation=True)
                    continue

                reading = SensorReading(
                    station_id=item["station_id"],
                    district_id=item["district_id"],
                    sensor_type=item["sensor_type"],
                    data=item["data"],
                    reading_id=item.get("id"),
                    timestamp=item.get("timestamp"),
                    geo_location=item.get("geo_location")
                )
                
                try:
                    dispatch_queue.put_nowait(reading.to_dict())
                    accepted += 1
                except queue.Full:
                    metrics.record_error(is_validation=False)

            latency_ms = (time.time() - start_t) * 1000.0
            metrics.record_success(latency_ms)

            self._send_json(202, {
                "status": "ACCEPTED",
                "processed_items": accepted,
                "latency_ms": round(latency_ms, 2)
            })
        else:
            self._send_json(404, {"error": "Endpoint Not Found"})

    def log_message(self, format, *args):
        return

def run_server():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), IngestionHTTPHandler)
    print(f"[IngestionService] Running on port {PORT}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[IngestionService] Shutting down...")
        server.server_close()

if __name__ == "__main__":
    run_server()
