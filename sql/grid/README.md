# a4i_grid — the Brooklyn analysis grid

Every number the model, the agent and the portal use hangs off one grid: cells of
**0.001° × 0.001°** (≈110 m × 85 m in Brooklyn), keyed by two integers.

```
cell_i = FLOOR(lat / 0.001)      centre lat = (cell_i + 0.5) * 0.001
cell_j = FLOOR(lon / 0.001)      centre lon = (cell_j + 0.5) * 0.001
```

To find the cell for any point (an address, a click on the map), apply the same two
`FLOOR`s and look up `(cell_i, cell_j)`.

Rebuild everything (≈1 minute, safe to re-run):

```bash
bash sql/grid/build.sh <project-id>
```

## Three layers on one base

| Layer | Question it answers | Tables | Rows |
|---|---|---|---:|
| **Base** | Which cells exist, and can we trust a prediction there? | `cells` | 29,503 |
| **Heat** | How much hotter is this spot, and how often is that dangerous? | `cell_readings`, `cell_heat`, `heat_reference_daily`, `city_heat_history`, `cell_heat_history` | 15,105 readings → 1,020 cells |
| **Built environment** | What about this place makes it hot? (model features) | `cell_built` | 29,503 |
| **Impact** | Who lives here, and how exposed are they? | `cell_impact` ← `blockgroup_exposure`, `tract_exposure` | 29,503 |

Views: `training_examples` (features + label), `cell_heat_summary` (history rolled up per
cell), `cell_profile` (everything about a cell in one row: what the portal and the agent read).

## Heat layer

- **`cell_readings`**: every Heat Watch reading tagged with its cell, with `offset_f`
  (reading minus the campaign mean). The full measured record.
- **`cell_heat`**: one row per driven cell with ≥ 5 readings. `offset_f` is the **BigQuery
  ML label**. `holdout` marks whole 10×10-cell blocks (≈1 km) held out together.
- **`heat_reference_daily`** / **`city_heat_history`**: the daily high averaged over
  Central Park, LaGuardia and JFK, 2019–2025, and days per year at or above 90/95/100°F.
- **`cell_heat_history`**: estimated days ≥ 90/95/100°F per cell per year,
  using *reference daily high + the cell's offset*.

> **Say this out loud:** a cell has one afternoon of measurements, not a history. The
> per-cell history assumes that afternoon's offset holds on every hot day — the notebook's
> own premise, but an estimate, not a measurement. Only driven cells have it today; undriven
> cells get it once the model predicts their offset.

What it shows: the city averaged ~2 days a year at 95°F+, but the estimate per driven cell
ranges from 0.3 to 11 days a year. The trend over 7 years is too short to call.

## Built-environment layer (model features)

Only things computable for a cell nobody drove through:

| Feature | Source | Corr. with offset |
|---|---|---:|
| `tract_water_share` | Tract water area — waterfront proxy | −0.29 |
| `dist_open_space_m` | Distance to near-empty large tracts (parks, cemeteries, airfield) | −0.20 |
| `bg_housing_units_per_km2` | Block-group housing density | −0.08 |
| `trees_50m/100m/250m`, `tree_dbh_sum_100m` | 2015 street tree census | −0.06 |

**Next: EPA Smart Location Database.** Join on `bg_geo_id` (EPA's `GEOID10` is the same
12-character 2010 block-group ID) and add its density, land-use mix, intersection density
and `NatWalkInd` columns to `08_cell_built.sql`. Also missing: distance to shoreline.

## Impact layer (never a model input)

Demographics stay out of the model so the equity audit isn't circular (the model would learn
"poor tract → hot" and the audit would then confirm it).

| Prefix | Level | Source | Columns |
|---|---|---|---|
| `bg_` | Block group (Brooklyn: 2,085) | ACS 2018 5-yr | population, share 65+, median age, income, renter share, severe rent burden (>50% of income), density |
| `tract_` | Tract (Brooklyn: 761) | ACS 2019 5-yr | no-vehicle rate, poverty rate — block-group ACS lacks both |
| `est_` | Cell | allocated | `est_residents`, `est_residents_65_plus`, `est_households_no_car` |

`est_*` spreads each block group evenly over its land cells, so sums over any set of cells
don't double count (Brooklyn: 2.60M residents, 343k aged 65+, 529k households without a car).

Cleaning decisions are in the header of each SQL file. The ones worth knowing:
- Census "not available" sentinels (e.g. −666,666,666) become NULL.
- 2010 boundaries throughout, because the BigQuery geometry tables use them.
- In the 2019 tract ACS, `households` is empty (we use `occupied_housing_units`, which equals
  it) and `female_65_to_66` is empty (estimated from men 65–66 × the tract's female/male ratio
  at 67–69).

## Training a model

```sql
CREATE OR REPLACE MODEL a4i_grid.heat_offset_v1
OPTIONS (model_type = 'LINEAR_REG', input_label_cols = ['offset_f']) AS
SELECT * EXCEPT (cell_i, cell_j, holdout, n_readings)
FROM a4i_grid.training_examples
WHERE NOT holdout;

SELECT * FROM ML.EVALUATE(MODEL a4i_grid.heat_offset_v1,
  (SELECT * EXCEPT (cell_i, cell_j, holdout, n_readings)
   FROM a4i_grid.training_examples WHERE holdout));
```

Then `ML.EXPLAIN_PREDICT` over `cell_built` for land cells. Flag predictions where
`cells.in_training_range` is false: 44% of Brooklyn's land cells are more than 1 km from
any driven cell, so the model is extrapolating there.
