import os
import sys
import time
import random
import json
import urllib.request
import urllib.error

INGESTION_URL = os.environ.get("INGESTION_URL", "http://127.0.0.1:8001/api/telemetry")
PUBLISH_INTERVAL_SEC = float(os.environ.get("PUBLISH_INTERVAL_SEC", 0.5))
TOTAL_MESSAGES = int(os.environ.get("TOTAL_MESSAGES", 0))

DISTRICTS = [
    {"id": "central", "lat": 49.5883, "lon": 34.5514, "traffic_base": 65, "pm25_base": 32.0},
    {"id": "industrial", "lat": 49.6050, "lon": 34.5820, "traffic_base": 40, "pm25_base": 55.0},
    {"id": "residential", "lat": 49.5720, "lon": 34.5240, "traffic_base": 30, "pm25_base": 18.0},
    {"id": "waterfront", "lat": 49.5630, "lon": 34.5700, "traffic_base": 25, "pm25_base": 12.0},
    {"id": "suburban", "lat": 49.6200, "lon": 34.5100, "traffic_base": 20, "pm25_base": 10.0},
]

def generate_telemetry_event() -> dict:
    district = random.choice(DISTRICTS)
    sensor_type = random.choice(["environmental", "traffic"])
    station_num = random.randint(1, 10)
    station_id = f"STN-{district['id'].upper()[:3]}-{station_num:02d}"

    is_anomaly = random.random() < 0.12

    if sensor_type == "environmental":
        pm25 = district["pm25_base"] + random.gauss(0, 5)
        if is_anomaly:
            pm25 += random.uniform(40, 130)
        pm25 = max(2.0, round(pm25, 2))

        co2 = 450 + random.randint(-30, 150)
        if is_anomaly and district["id"] == "industrial":
            co2 += random.randint(600, 1000)

        noise = random.randint(45, 72)
        if is_anomaly and district["id"] in ("central", "industrial"):
            noise += random.randint(12, 22)

        data = {
            "pm25": pm25,
            "pm10": round(pm25 * 1.6, 2),
            "co2": co2,
            "noise_db": noise,
            "temperature_c": round(18.0 + random.uniform(-4, 6), 1),
            "humidity_pct": random.randint(40, 85)
        }
    else:
        congestion = district["traffic_base"] + random.randint(-15, 15)
        speed = 55.0 - (congestion * 0.4) + random.uniform(-5, 5)
        
        if is_anomaly:
            congestion = random.randint(80, 98)
            speed = random.uniform(5.0, 14.0)

        congestion = max(5, min(100, int(congestion)))
        speed = max(3.0, round(speed, 1))
        vehicle_count = int(congestion * 1.8 + random.randint(-5, 15))

        data = {
            "vehicle_count_per_min": max(1, vehicle_count),
            "avg_speed_kmh": speed,
            "congestion_index": congestion
        }

    return {
        "station_id": station_id,
        "district_id": district["id"],
        "sensor_type": sensor_type,
        "timestamp": time.time(),
        "geo_location": {
            "lat": round(district["lat"] + random.uniform(-0.005, 0.005), 5),
            "lon": round(district["lon"] + random.uniform(-0.005, 0.005), 5)
        },
        "data": data
    }

def send_event(event: dict) -> bool:
    try:
        body = json.dumps(event).encode("utf-8")
        req = urllib.request.Request(
            INGESTION_URL,
            data=body,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status in (200, 201, 202)
    except Exception:
        return False

def main():
    print(f"[Simulator] Starting IoT Smart City sensor telemetry feed to {INGESTION_URL}")
    print(f"[Simulator] Interval: {PUBLISH_INTERVAL_SEC}s, Districts: {len(DISTRICTS)}")
    count = 0
    success = 0
    
    while True:
        event = generate_telemetry_event()
        ok = send_event(event)
        count += 1
        if ok:
            success += 1

        if count % 20 == 0:
            print(f"[Simulator] Generated {count} events ({success} delivered successfully)")

        if TOTAL_MESSAGES > 0 and count >= TOTAL_MESSAGES:
            print(f"[Simulator] Finished sending {TOTAL_MESSAGES} messages.")
            break

        time.sleep(PUBLISH_INTERVAL_SEC)

if __name__ == "__main__":
    main()
