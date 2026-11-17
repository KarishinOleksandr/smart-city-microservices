import os
import sys
import time
import subprocess
import signal

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def start_services():
    env = os.environ.copy()
    env["PYTHONPATH"] = BASE_DIR

    print("Starting Smart City Microservices Locally...")

    p_storage = subprocess.Popen(
        [sys.executable, os.path.join(BASE_DIR, "storage_service", "main.py")],
        env=dict(env, PORT="8003")
    )
    print("Storage Service launched PID:", p_storage.pid)

    p_proc = subprocess.Popen(
        [sys.executable, os.path.join(BASE_DIR, "processing_service", "main.py")],
        env=dict(env, PORT="8002")
    )
    print("Processing Service launched PID:", p_proc.pid)

    time.sleep(1.0)

    p_ingest = subprocess.Popen(
        [sys.executable, os.path.join(BASE_DIR, "ingestion_service", "main.py")],
        env=dict(
            env,
            PORT="8001",
            PROCESSING_SERVICE_URL="http://127.0.0.1:8002/api/events",
            STORAGE_SERVICE_URL="http://127.0.0.1:8003/api/telemetry"
        )
    )
    print("Ingestion Gateway launched PID:", p_ingest.pid)

    processes = [p_storage, p_proc, p_ingest]

    try:
        print("Microservices running. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
            for p in processes:
                if p.poll() is not None:
                    print(f"Warning: Process {p.pid} exited.")
    except KeyboardInterrupt:
        print("Stopping microservices...")
        for p in processes:
            p.terminate()
            p.wait()
        print("Done.")

if __name__ == "__main__":
    start_services()
