FROM python:3.11-slim
WORKDIR /app

RUN adduser --disabled-password --gecos "" myuser
USER myuser

ENV PATH="/home/myuser/.local/bin:$PATH"
ENV GOOGLE_GENAI_USE_VERTEXAI=1
ENV GOOGLE_CLOUD_PROJECT=qwiklabs-gcp-04-ec3596addc43
ENV GOOGLE_CLOUD_LOCATION=global
ENV COMPUTE_REGION=us-central1
ENV BQ_LOCATION=US
ENV CITY=Atlanta
ENV TRACK=budget
ENV SCENARIO_SITES=3
ENV BQML_MODEL_ID=offset_model_v1
ENV AGENT_MODEL=gemini-3-flash-preview
ENV WRITER_MODEL=gemini-3-flash-preview

COPY --chown=myuser:myuser "agent/requirements.txt" "/app/requirements.txt"
RUN pip install --no-cache-dir -r "/app/requirements.txt"

COPY --chown=myuser:myuser "agent/" "/app/agents/urban_heat_agent/"
ENV PYTHONPATH="/app/agents/urban_heat_agent:/app/agents"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "heat_planner.api:app", "--host", "0.0.0.0", "--port", "8000"]
