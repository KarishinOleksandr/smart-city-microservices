FROM python:3.11-slim

WORKDIR /app

COPY sensor_simulator /app/sensor_simulator

ENV PYTHONUNBUFFERED=1
ENV INGESTION_URL=http://ingestion-service:8001/api/telemetry
ENV PUBLISH_INTERVAL_SEC=0.5

CMD ["python", "sensor_simulator/main.py"]
