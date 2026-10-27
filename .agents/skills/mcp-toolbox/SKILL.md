---
name: mcp-toolbox
description: Configures and deploys MCP Toolbox for Databases (Google's managed, open-source MCP server) against the team's BigQuery datasets on Cloud Run with min-instances 1, and connects it to the ADK agent and to the Antigravity CLI itself. Use when writing tools.yaml, adding a parameterized SQL tool, deploying or debugging the Toolbox service, or choosing between Toolbox and BigQuery's built-in MCP server.
---

# MCP Toolbox for Databases

The challenge requires **consuming** a managed MCP server, not authoring one. Toolbox is the
recommended choice: prebuilt BigQuery tools *and* your own parameterized SQL tools, with
access shaped by `tools.yaml` + IAM.

## Decision: Toolbox vs BigQuery built-in MCP

| | Toolbox (recommended) | BigQuery managed MCP |
|---|---|---|
| Setup | Container on Cloud Run | Enable on the project; Google hosts it |
| Custom tools | Yes: named, parameterized SQL with descriptions | Generic query/list tools only |
| Access control | Own service account + curated toolset | Caller's identity |
| Demo risk | Cold start (fix: `--min-instances=1`) | None to host |

Record the choice in `docs/DECISIONS.md`. A valid split: **Toolbox for curated read-only data
tools** (frequency, tract lookup, schema discovery) + **Python tools for anything with shape**
(explain/rank/assemble). The README explicitly accepts `ML.EXPLAIN_PREDICT` as a Toolbox SQL
tool too. If you do that, it counts as "a tool you built", but Python is better for turning
attributions into planner language.

## tools.yaml

Start from `resources/tools.yaml`. Rules:
- Every tool has a **description written for the LLM** (when to use it, units, caveats).
- Parameters are typed and described. Statements use `@param`, never string templating.
- Read-only by construction: `toolbox-sa` has only `bigquery.dataViewer` on the two datasets
  plus `bigquery.jobUser`, so even a generic `execute_sql` tool can't write. IAM is the
  guardrail; the YAML is the UX.
- Group tools into a toolset (`heat-planner`) and load only that toolset in the agent.

Validate locally before deploying (Cloud Shell has Docker):
```bash
docker run --rm -p 5000:5000 -v "$PWD/toolbox:/cfg" \
  -v "$HOME/.config/gcloud:/root/.config/gcloud:ro" \
  "$TOOLBOX_IMAGE" --tools-file=/cfg/tools.yaml --address=0.0.0.0 --port=5000
curl -s localhost:5000/api/toolset/heat-planner | head    # lists tools if YAML parsed
```
The YAML schema has changed across Toolbox releases. If it fails to parse, check the docs for
**the pinned image version** before editing blindly.

## Deploy (Cloud Run, private, warm)

`/gcp-platform` → `scripts/deploy_toolbox.sh`. It stores `tools.yaml` in Secret Manager, deploys
the **pinned** Toolbox image with `toolbox-sa`, `--no-allow-unauthenticated`, `--min-instances=1`,
and grants `heat-agent-sa` (and the Agent Runtime service agent) `roles/run.invoker`.

Smoke test:
```bash
URL=$(gcloud run services describe heat-toolbox --region "$REGION" --format='value(status.url)')
curl -s -H "Authorization: Bearer $(gcloud auth print-identity-token)" "$URL/api/toolset/heat-planner" | head
```

## Connect the ADK agent

Set `TOOLBOX_URL=$URL`. `adk-agent/examples/agent.py` attaches it as an `McpToolset` over
Streamable HTTP at `$URL/mcp`, with a Google ID token header. The agent must still boot if the
Toolbox is down (feature flag + try/except).

## Give the coding agent (agy) BigQuery access during development

`.agents/mcp_config.json` (installed by `install.sh`) runs Toolbox locally over stdio with the
prebuilt BigQuery toolset, using your Cloud Shell ADC. That lets agy run `INFORMATION_SCHEMA`
checks and draft SQL against real tables. This is a dev convenience and separate from the
product's MCP server. Don't present it as the product's MCP usage.
