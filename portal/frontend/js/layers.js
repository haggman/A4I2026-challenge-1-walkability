// Map layer catalogue. One entry per thing the map can be coloured by.
//
//   source  "cell"  -> a column of a4i_grid.cell_profile (0.001° squares)
//           "tract" -> a column of a4i_grid.tract_exposure (census tract polygons)
//   domain  fixed [min, (mid,) max], or omitted to use the data's 2nd-98th percentile
//   status  "ready" | "needs_model" -- disabled layers show up greyed out with the reason
//
// To add a feature: add the column to CELL_COLUMNS / TRACT_COLUMNS in backend/data.py,
// refresh the snapshot, and add an entry here.

const HEAT = ["#2166ac", "#4393c3", "#92c5de", "#f7f7f7", "#f4a582", "#d6604d", "#b2182b"];
const GREENS = ["#f7fcf5", "#c7e9c0", "#74c476", "#238b45", "#00441b"];
const BLUES = ["#f7fbff", "#c6dbef", "#6baed6", "#2171b5", "#08306b"];
const PURPLES = ["#fcfbfd", "#dadaeb", "#9e9ac8", "#6a51a3", "#3f007d"];
const ORANGES = ["#fff5eb", "#fdd0a2", "#fd8d3c", "#d94801", "#7f2704"];
const GREYS = ["#ffffff", "#bdbdbd", "#737373", "#252525"];

export const LAYER_GROUPS = [
  {
    label: "Heat",
    layers: [
      {
        id: "offset_f", source: "cell", label: "Campaign heat difference", unit: "°F",
        palette: HEAT, domain: [-3, 0, 3], format: (v) => `${v > 0 ? "+" : ""}${v.toFixed(1)}°F`,
        note: "Relative difference from the citywide campaign average, not the actual air temperature. Measured on one afternoon in surveyed blocks only.",
      },
      {
        id: "heat_index_offset_f", source: "cell", label: "Campaign feels-like difference", unit: "°F",
        palette: HEAT, domain: [-3, 0, 3], format: (v) => `${v > 0 ? "+" : ""}${v.toFixed(1)}°F`,
        note: "Relative heat-index difference including humidity, not the actual feels-like temperature. Measured on one afternoon in surveyed blocks only.",
      },
      {
        id: "est_days_ge_95_per_year", source: "cell", label: "Estimated days ≥ 95°F per year", unit: "days",
        palette: ORANGES, format: (v) => v.toFixed(1),
        note: "City reference high + this block's offset, averaged over 2019–2025. An estimate: assumes the one-afternoon offset holds on every hot day.",
      },
      {
        id: "trend_days_ge_95_per_year", source: "cell", label: "Trend in days ≥ 95°F", unit: "days/yr",
        palette: HEAT, domain: [-2, 0, 2], format: (v) => `${v > 0 ? "+" : ""}${v.toFixed(1)}/yr`,
        note: "Slope over 7 years. Too short a record to call a real trend; show with care.",
      },
      {
        id: "predicted_offset", source: "cell", label: "Predicted heat offset", unit: "°F",
        status: "needs_model",
        note: "Appears once the BQML model scores every cell (ML.EXPLAIN_PREDICT).",
      },
    ],
  },
  {
    label: "Built environment (model features)",
    layers: [
      { id: "trees_100m", source: "cell", label: "Street trees within 100 m", unit: "trees",
        palette: GREENS, format: (v) => v.toFixed(0) },
      { id: "trees_250m", source: "cell", label: "Street trees within 250 m", unit: "trees",
        palette: GREENS, format: (v) => v.toFixed(0) },
      { id: "tree_dbh_sum_100m", source: "cell", label: "Trunk diameter within 100 m", unit: "in",
        palette: GREENS, format: (v) => v.toFixed(0),
        note: "Summed diameter at breast height: a rough stand-in for canopy size." },
      { id: "dist_open_space_m", source: "cell", label: "Distance to large open space", unit: "m",
        palette: ORANGES, format: (v) => `${(v / 1000).toFixed(1)} km`,
        note: "Parks, cemeteries and airfields (near-empty tracts). A proxy, not a park layer." },
      { id: "tract_water_share", source: "cell", label: "Water share of tract", unit: "",
        palette: BLUES, format: (v) => `${(v * 100).toFixed(0)}%`,
        note: "Waterfront proxy. Strongest single correlate of the offset so far (r = −0.29)." },
      { id: "bg_housing_units_per_km2", source: "cell", label: "Housing density (block group)", unit: "units/km²",
        palette: PURPLES, format: (v) => Math.round(v).toLocaleString() },
    ],
  },
  {
    // Block-group columns (bg_*) are ACS 2018; car ownership and poverty only exist per tract (ACS 2019).
    label: "Who lives there (not model inputs)",
    layers: [
      { id: "bg_share_65_plus", source: "cell", label: "Residents 65+", palette: ORANGES,
        format: (v) => `${(v * 100).toFixed(0)}%`, note: "Block group, ACS 2018." },
      { id: "est_residents_65_plus", source: "cell", label: "Estimated residents 65+ in this block", unit: "people",
        palette: ORANGES, format: (v) => v.toFixed(0),
        note: "Block group's 65+ population spread evenly over its land cells. Adds up across cells without double counting." },
      { id: "tract_no_vehicle_rate", source: "cell", label: "Households without a car", palette: ORANGES,
        format: (v) => `${(v * 100).toFixed(0)}%`, note: "Tract, ACS 2019 (not published per block group)." },
      { id: "tract_poverty_rate", source: "cell", label: "Poverty rate", palette: ORANGES,
        format: (v) => `${(v * 100).toFixed(0)}%`, note: "Tract, ACS 2019." },
      { id: "bg_median_income", source: "cell", label: "Median household income", palette: PURPLES,
        format: (v) => `$${Math.round(v / 1000)}k`, note: "Block group, ACS 2018." },
      { id: "bg_severe_rent_burden_rate", source: "cell", label: "Severely rent-burdened renters", palette: ORANGES,
        format: (v) => `${(v * 100).toFixed(0)}%`,
        note: "Renters paying 50%+ of income on rent: less room for AC and power bills. Block group, ACS 2018." },
      { id: "bg_pop_per_km2", source: "cell", label: "Population density", unit: "people/km²",
        palette: PURPLES, format: (v) => Math.round(v).toLocaleString(), note: "Block group, ACS 2018." },
    ],
  },
  {
    label: "Model coverage",
    layers: [
      { id: "dist_to_driven_m", source: "cell", label: "Distance to nearest measured block", unit: "m",
        palette: GREYS, domain: [0, 3000], format: (v) => `${Math.round(v)} m`,
        note: "Beyond ~1 km the model is extrapolating. Say so when you show a prediction there." },
    ],
  },
];

export const OVERLAYS = [
  { id: "tract-lines", label: "Census tract boundaries", on: true },
  { id: "driven-outline", label: "Outline measured blocks", on: false },
  { id: "out-of-range", label: "Grey out blocks >1 km from a measurement", on: false },
  { id: "holdout", label: "Highlight held-out test blocks", on: false },
  { id: "non-land", label: "Show water / non-residential cells", on: false },
];

// Public-domain basemaps (US Government works) -- avoids the ODbL question that
// OpenStreetMap-based tiles would raise. Max native zoom is 16.
export const BASEMAPS = [
  { id: "topo", label: "Streets",
    url: "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}" },
  { id: "imagery", label: "Imagery",
    url: "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}" },
  { id: "none", label: "None", url: null },
];

export function findLayer(id) {
  for (const g of LAYER_GROUPS) for (const l of g.layers) if (l.id === id) return l;
  return null;
}
