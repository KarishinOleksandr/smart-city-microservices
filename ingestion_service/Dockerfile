FROM python:3.11-slim

WORKDIR /app

COPY common /app/common
COPY ingestion_service /app/ingestion_service

ENV PYTHONUNBUFFERED=1
ENV PORT=8001

EXPOSE 8001

CMD ["python", "ingestion_service/main.py"]
