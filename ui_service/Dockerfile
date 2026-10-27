# heat-ui (IMPLEMENTATION_PLAN.md Stage 3). Build context is ui_service/:
#   gcloud run deploy heat-ui --source=ui_service ...
FROM python:3.11-slim
WORKDIR /app

RUN adduser --disabled-password --gecos "" myuser

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY --chown=myuser:myuser . /app/ui_service/

USER myuser
ENV PORT=8080 CITY_NAME=Atlanta
EXPOSE 8080
# AGENT_API_URL is set at deploy time; without it the service runs on samples/ (mock banner shown).
CMD exec uvicorn ui_service.main:app --host 0.0.0.0 --port ${PORT}
