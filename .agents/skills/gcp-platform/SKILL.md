---
name: gcp-platform
description: Sets up and operates the team's Google Cloud infrastructure for the heat planner. It enables APIs, creates least-privilege service accounts and dataset grants, Secret Manager entries, and deploys the ADK agent to Agent Runtime (formerly Agent Engine) or Cloud Run and MCP Toolbox to Cloud Run, with tracing, logging, labels and cost guardrails. Use for bootstrap, any deploy, IAM/permission errors, cold starts, or choosing Agent Runtime vs Cloud Run.
---

# GCP platform: bootstrap, deploy, operate

You are acting as the **platform engineer / SRE**. Goal: a deployed, warm, observable agent
by the end of the Deploy phase, using the least privilege that still works, with nothing that
can surprise anyone on stage.

## Reference architecture

```
                    ┌──────────────── Google Cloud project (one per team) ───────────────┐
 Planner ──► UI ───►│ Agent Runtime (or Cloud Run)  heat-planner        sa: heat-agent-sa │
  adk web /         │   ADK root_agent ── Gemini (Gemini platform, us-central1)           │
  Gemini Ent. /     │      │ Python tools ── BigQuery jobs ─► a4i_ml.offset_model_vN      │
  custom Cloud Run  │      │                                  (ML.EXPLAIN_PREDICT)        │
                    │      └ McpToolset ──ID token──► Cloud Run heat-toolbox (min=1)      │
                    │                                  sa: toolbox-sa  (read-only BQ)     │
                    │ BigQuery (US): a4i_climate (raw) · a4i_ml (features, models, grid)  │
                    │ Secret Manager: toolbox tools.yaml, maps key                        │
                    │ Cloud Logging · Cloud Trace (adk --trace_to_cloud) · labels app=…   │
                    └────────────────────────────────────────────────────────────────────┘
```

## Choose the agent runtime (decide in Build, record why)

| If… | Choose | Why |
|---|---|---|
| Front end is **Gemini Enterprise** | **Agent Runtime** | Gemini Enterprise surfaces Agent Runtime agents; managed sessions; least code |
| Front end is a **custom UI** or `adk web` UI for the demo | **Cloud Run** (`adk deploy cloud_run --with_ui`) | A URL you control, the same container locally and deployed, `min-instances=1` |
| Unsure | Cloud Run first | Fastest feedback loop; Agent Runtime can follow |

## Scripts (in `scripts/`, copy to the team repo's `infra/`)

| Script | What | Idempotent |
|---|---|---|
| `bootstrap.sh` | APIs, service accounts, IAM, `a4i_ml` dataset, dataset-scoped grants via BigQuery DCL, labels | yes |
| `deploy_toolbox.sh` | Secret → Cloud Run `heat-toolbox` (pinned image, private, min=1) → invoker grants | yes |
| `deploy_agent.sh` | `cloud_run` or `agent_runtime` target; sets SA, env, min instances, tracing | yes |
| `smoke.sh` | Hits the deployed agent with 2 planner questions; fails loudly | yes |

All read `PROJECT_ID`, `REGION` (default `us-central1`) and `TEAM` from env.

## IAM model (least privilege, no keys)

| Principal | Roles | Scope |
|---|---|---|
| `heat-agent-sa` | `bigquery.jobUser`, `aiplatform.user`, `logging.logWriter`, `cloudtrace.agent` | project |
| `heat-agent-sa` | `bigquery.dataViewer` | datasets `a4i_climate`, `a4i_ml` (DCL `GRANT … ON SCHEMA`) |
| `heat-agent-sa` | `run.invoker` | service `heat-toolbox` |
| `toolbox-sa` | `bigquery.jobUser` (project) + `bigquery.dataViewer` (two datasets) | |
| Agent Runtime service agent `service-<NUM>@gcp-sa-aiplatform-re.iam.gserviceaccount.com` | same as `heat-agent-sa` | only if deploying to Agent Runtime without a custom SA |
| Humans | Owner (given by the lab) | |

Permission error triage: read the *principal* in the error message. It's usually the runtime
SA or the Agent Runtime service agent missing `bigquery.jobUser`, or dataViewer on `a4i_ml`.

## Reliability checklist (demo day is production)

- [ ] `--min-instances=1` on every Cloud Run service that is demoed; `--cpu-boost`.
- [ ] Pinned image tags / package versions; deploy is reproducible from `main`.
- [ ] Smoke test passes against the **deployed** URL from the **presenting** laptop.
- [ ] Model promotion = config change (`BQML_MODEL_ID`) + redeploy; the previous model is kept.
- [ ] A screenshot/recording of a good run exists (fallback if live fails).
- [ ] Logs: `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="heat-planner"' --limit 50`.
- [ ] Traces visible in Cloud Trace (deployed with `--trace_to_cloud`).

## Cost guardrails

- `maximum_bytes_billed` on every query (agent config: 1 GB).
- `LINEAR_REG` (free tier). Anything else is a recorded decision.
- Labels `team`, `app=heat-planner`, `env=hackathon` on every resource → billing breakdown.
- After the event, scale `min-instances` to 0 (`scripts/teardown.sh` prints the commands; it doesn't run them).

## Version caveat

`adk deploy` flags (`agent_engine` vs newer names, `--staging_bucket`, `--env_file`,
`--service_account`) differ by ADK release. Run `adk deploy --help` / `adk deploy <target> --help`
with the **pinned** version and adapt `deploy_agent.sh`. Don't guess flags.
