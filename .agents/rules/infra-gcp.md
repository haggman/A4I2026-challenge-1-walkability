---
trigger: glob
globs: "infra/**, **/Dockerfile, **/cloudbuild.yaml, toolbox/**"
description: GCP infrastructure conventions (IAM, Cloud Run, Agent Runtime, secrets).
---

# GCP infrastructure conventions

- Scripts are idempotent bash: `set -euo pipefail`, read `PROJECT_ID`/`REGION` from env or
  `gcloud config`, check existence before create, `--quiet` on mutating commands.
- Service accounts: `heat-agent-sa` (agent runtime), `toolbox-sa` (MCP Toolbox). Grant
  `roles/bigquery.jobUser` at project level and `roles/bigquery.dataViewer` **on the dataset
  only**. Agent SA also gets `roles/aiplatform.user` and `roles/run.invoker` on the Toolbox service.
- No key files. Cloud Run uses `--service-account`. Local dev uses `gcloud auth application-default login`.
- Secrets (Toolbox `tools.yaml` if it holds anything sensitive, Maps API key) live in Secret
  Manager and are mounted with `--set-secrets`. Never pass them as plain `--set-env-vars`.
- Cloud Run defaults for anything that's demoed: `--min-instances=1`, `--cpu-boost`,
  `--timeout=300`, `--concurrency=40`, explicit `--memory`. Pin image tags, never `:latest`.
- Label everything: `--labels=team=${TEAM},app=heat-planner,env=hackathon`.
- Ask the human before any `delete`, `rm`, IAM removal, or change to a resource another lane created.
