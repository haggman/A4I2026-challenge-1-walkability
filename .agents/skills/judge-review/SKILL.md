---
name: judge-review
description: Runs a read-only, judge's-eye audit of the team repo and submission against the A4I Challenge 1 rubric and non-negotiables (offset framing, BQML actually called, MCP consumed, built tool, deployed, race excluded, audit done, limitations stated, licenses checked, no secrets). Use before each phase gate, before merging to main, and before recording the pitch video.
---

# Judge review (read-only)

Act as a skeptical judge with the repo, deck and video in hand and no chance to ask questions.
**Do not modify files.** Produce a findings table, most severe first.

## Checklist (verify each by reading code or running a read-only command; cite file:line)

**Hard requirements**
- [ ] An agent tool calls `ML.EXPLAIN_PREDICT` (or `ML.PREDICT`) on a BQML model. `grep -rn "EXPLAIN_PREDICT" agent/`
- [ ] At least one managed MCP server consumed (Toolbox or BigQuery MCP) in agent code
- [ ] At least one tool the team designed (Python function tool or custom Toolbox tool)
- [ ] Deployed: a URL or Agent Runtime resource exists and answers (`infra/smoke.sh`)
- [ ] ADK + Gemini + BigQuery all genuinely used

**Rigor**
- [ ] Label is an offset; no response template says "it will be N° here" as a measurement
- [ ] No drive-day columns (`temp_f`, `heat_index_f`, `humidity_pct`, `observed_at`) in features
- [ ] Spatial (not random) eval split; metrics compared to a baseline; numbers in DECISIONS.md
- [ ] No race/ethnicity columns in features/ranking; equity audit implemented and its result reported
- [ ] Validation results recorded; LPAD/SAFE_CAST used on public-data joins
- [ ] Refusal behaviour present in the system instruction and tested (evalset)
- [ ] Limitations stated in the agent output and the deck
- [ ] Every external dataset has source + license in DECISIONS.md; no OSM/ODbL, NC, ND, SA

**Engineering**
- [ ] No secrets/keys in git: `git grep -nE "AIza|BEGIN PRIVATE KEY|\"private_key\"|ya29\."`
- [ ] Least-privilege service accounts; no Owner on runtime identities
- [ ] Pinned versions; `min-instances=1` on demoed services
- [ ] README in the team repo explains how to run it, and names the track, city and interface choice

## Output format

| Severity | Area | Finding | Evidence | Fix (≤1 line) |
|---|---|---|---|---|

Severity: **Blocker** (requirement unmet) · **Major** (costs rubric points) · **Minor** (polish).
End with the three highest-leverage fixes for the remaining time.
