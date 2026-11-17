# Cloud Run image. Build from portal/:
#   gcloud run deploy heat-portal --source . --region us-central1 --min-instances 1
# The data/ snapshot is baked in if present; otherwise the first request builds it from
# BigQuery using the service account (needs BigQuery Data Viewer + Job User).
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30" \
    "google-cloud-bigquery>=3.25" "db-dtypes>=1.3"
COPY backend backend
COPY frontend frontend
COPY data data
ENV PORT=8080
CMD exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}
