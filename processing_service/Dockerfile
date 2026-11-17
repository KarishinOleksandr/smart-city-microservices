FROM python:3.11-slim

WORKDIR /app

COPY common /app/common
COPY processing_service /app/processing_service

ENV PYTHONUNBUFFERED=1
ENV PORT=8002

EXPOSE 8002

CMD ["python", "processing_service/main.py"]
