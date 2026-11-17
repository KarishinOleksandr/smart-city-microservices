import os
import sys
import json
import time
import threading
from collections import deque
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from common.models import AlertEvent

PORT = int(os.environ.get("PORT", 8002))

THRESHOLDS = {
    "pm25_warning": float(os.environ.get("TH_PM25_WARN", 50.0)),
    "pm25_critical": float(os.environ.get("TH_PM25_CRIT", 150.0)),
    "co2_warning": float(os.environ.get("TH_CO2_WARN", 1200.0)),
    "noise_warning": float(os.environ.get("TH_NOISE_WARN", 80.0)),
    "traffic_congestion_critical": float(os.environ.get("TH_CONGESTION_CRIT", 75.0)),
    "traffic_speed_low": float(os.environ.get("TH_SPEED_LOW", 15.0)),
}

class ProcessingState:
    def __init__(self):
        self.lock = threading.Lock()
        self.total_processed = 0
        self.alerts = deque(maxlen=500)
        self.district_stats = {
            "central": {"readings": 0, "sum_pm25": 0.0, "sum_speed": 0.0, "alerts_count": 0},
            "industrial": {"readings": 0, "sum_pm25": 0.0, "sum_speed": 0.0, "alerts_count": 0},
            "residential": {"readings": 0, "sum_pm25": 0.0, "sum_speed": 0.0, "alerts_count": 0},
            "waterfront": {"readings": 0, "sum_pm25": 0.0, "sum_speed": 0.0, "alerts_count": 0},
            "suburban": {"readings": 0, "sum_pm25": 0.0, "sum_speed": 0.0, "alerts_count": 0},
        }

    def process_reading(self, reading: dict) -> list[dict]:
        generated_alerts = []
        district = reading.get("district_id", "central").lower()
        sensor_type = reading.get("sensor_type")
        data = reading.get("data", {})
        station_id = reading.get("station_id", "unknown")

        with self.lock:
            self.total_processed += 1
            if district not in self.district_stats:
                self.district_stats[district] = {"readings": 0, "sum_pm25": 0.0, "sum_speed": 0.0, "alerts_count": 0}
            d_stat = self.district_stats[district]
            d_stat["readings"] += 1

            if sensor_type == "environmental":
                pm25 = data.get("pm25")
                if pm25 is not None:
                    d_stat["sum_pm25"] += pm25
                    if pm25 >= THRESHOLDS["pm25_critical"]:
                        alert = AlertEvent(
                            alert_type="AIR_QUALITY_CRITICAL",
                            severity="CRITICAL",
                            district_id=district,
                            station_id=station_id,
                            message=f"Critical PM2.5 level detected ({pm25} µg/m³)! Immediate smog warning.",
                            metric_name="pm25",
                            metric_value=pm25,
                            threshold_value=THRESHOLDS["pm25_critical"]
                        )
                        generated_alerts.append(alert.to_dict())
                    elif pm25 >= THRESHOLDS["pm25_warning"]:
                        alert = AlertEvent(
                            alert_type="AIR_QUALITY_WARNING",
                            severity="WARNING",
                            district_id=district,
                            station_id=station_id,
                            message=f"Elevated PM2.5 level ({pm25} µg/m³).",
                            metric_name="pm25",
                            metric_value=pm25,
                            threshold_value=THRESHOLDS["pm25_warning"]
                        )
                        generated_alerts.append(alert.to_dict())

                co2 = data.get("co2")
                if co2 is not None and co2 >= THRESHOLDS["co2_warning"]:
                    alert = AlertEvent(
                        alert_type="CO2_CONCENTRATION_WARNING",
                        severity="WARNING",
                        district_id=district,
                        station_id=station_id,
                        message=f"High CO2 level ({co2} ppm). Poor ventilation/emissions.",
                        metric_name="co2",
                        metric_value=co2,
                        threshold_value=THRESHOLDS["co2_warning"]
                    )
                    generated_alerts.append(alert.to_dict())

                noise = data.get("noise_db")
                if noise is not None and noise >= THRESHOLDS["noise_warning"]:
                    alert = AlertEvent(
                        alert_type="ACOUSTIC_NOISE_WARNING",
                        severity="WARNING",
                        district_id=district,
                        station_id=station_id,
                        message=f"Noise pollution threshold exceeded ({noise} dB).",
                        metric_name="noise_db",
                        metric_value=noise,
                        threshold_value=THRESHOLDS["noise_warning"]
                    )
                    generated_alerts.append(alert.to_dict())

            elif sensor_type == "traffic":
                speed = data.get("avg_speed_kmh")
                congestion = data.get("congestion_index")
                if speed is not None:
                    d_stat["sum_speed"] += speed

                if congestion is not None and speed is not None:
                    if congestion >= THRESHOLDS["traffic_congestion_critical"] and speed <= THRESHOLDS["traffic_speed_low"]:
                        alert = AlertEvent(
                            alert_type="TRAFFIC_JAM_CRITICAL",
                            severity="CRITICAL",
                            district_id=district,
                            station_id=station_id,
                            message=f"Severe traffic jam detected: Congestion={congestion}%, Avg speed={speed} km/h.",
                            metric_name="congestion_index",
                            metric_value=congestion,
                            threshold_value=THRESHOLDS["traffic_congestion_critical"]
                        )
                        generated_alerts.append(alert.to_dict())

            for a in generated_alerts:
                self.alerts.append(a)
                d_stat["alerts_count"] += 1

        return generated_alerts

    def get_summary(self):
        with self.lock:
            result = {}
            for d, stat in self.district_stats.items():
                r_count = stat["readings"]
                result[d] = {
                    "total_readings": r_count,
                    "avg_pm25": round(stat["sum_pm25"] / r_count, 2) if r_count > 0 else 0.0,
                    "avg_traffic_speed_kmh": round(stat["sum_speed"] / r_count, 2) if r_count > 0 else 0.0,
                    "total_alerts": stat["alerts_count"]
                }
            return result

    def get_recent_alerts(self, limit: int = 50):
        with self.lock:
            items = list(self.alerts)
            return items[-limit:]

state = ProcessingState()

class ProcessingHTTPHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: dict):
        response_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_GET(self):
        if self.path == "/healthz":
            self._send_json(200, {"status": "UP", "total_processed": state.total_processed})
        elif self.path == "/api/district-summary":
            self._send_json(200, state.get_summary())
        elif self.path.startswith("/api/alerts"):
            self._send_json(200, {"alerts": state.get_recent_alerts()})
        elif self.path == "/metrics":
            self._send_json(200, {
                "service": "Processing-Rules-Service",
                "total_processed": state.total_processed,
                "total_alerts_emitted": len(state.alerts)
            })
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        if self.path == "/api/events":
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

            alerts = state.process_reading(reading)
            self._send_json(200, {
                "status": "PROCESSED",
                "generated_alerts_count": len(alerts),
                "alerts": alerts
            })
        else:
            self._send_json(404, {"error": "Endpoint Not Found"})

    def log_message(self, format, *args):
        return

def run_server():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), ProcessingHTTPHandler)
    print(f"[ProcessingService] Running on port {PORT}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[ProcessingService] Shutting down...")
        server.server_close()

if __name__ == "__main__":
    run_server()
