---
name: equity-audit
description: Runs the post-hoc equity audit of the agent's recommendations. It compares the census tracts where recommended sites landed against the population-weighted city on poverty, car access, age, income, and optionally race composition, as an output check only, never a model input. Use when building the run_equity_audit tool, preparing the audit slide, or answering "did we reach the neighborhoods that need this most?".
---

# Equity audit: strip the variable, audit the outcome, say you did both

Removing race from the model does **not** make it unbiased. Every proxy is still there. The
audit checks *where the recommendations landed* and who lives there. Judges look for this
explicitly (Rigor & judgment), and most teams skip it. Make it a centerpiece.

## Method (≈20 minutes)

1. Take the recommended sites (`state["last_ranked_sites"]`, or the top 10 from `grid_predictions`).
2. Map each to its tract (nearest centroid). De-duplicate tracts.
3. Compare **site tracts** vs. **the city**, both **population-weighted**:
   median income, poverty rate, no-vehicle rate, median age, plus share of population in the
   city's top-quintile-poverty tracts.
4. Report ratios and a plain-English finding. Either outcome is a result:
   - Sites skew poorer / less car access / older → evidence the model finds real vulnerability.
   - Sites skew the other way → "our features capture where it's **hot**, not where heat
     **hurts**." That's a genuine finding, so present it and show the re-weighted ranking.
5. **Sensitivity:** re-run the ranking with hazard-only weights vs. track weights and show how
   the audit changes. This turns the audit from a slide into a demonstrated design lever.

## SQL (`resources/audit.sql`)

`@site_geo_ids ARRAY<STRING>` → one row per metric: `sites_value`, `city_value`, `ratio`.

## Race, the one place it belongs

You *may* compare racial composition of recommended tracts vs. the city as an **output
check**, pulling ACS race columns directly in `sql/audit/` only (they are not in
`tract_demographics` by design). Never feed them back into ranking. If you do this, say exactly
that in the deck: "used only to audit, after the fact."

## What to show

One small table + one sentence with numbers, e.g.:
"Our 4 sites serve tracts with **1.8×** the city's share of car-free households and **1.4×** its
poverty rate. Median age matches the city (0.98×). Heat-only ranking would have picked
2 sites in higher-income tracts, so we weight car access for the Today track."
