FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir azure-cosmos

COPY common /app/common
COPY storage_service /app/storage_service

ENV PYTHONUNBUFFERED=1
ENV PORT=8003

EXPOSE 8003

CMD ["python", "storage_service/main.py"]
