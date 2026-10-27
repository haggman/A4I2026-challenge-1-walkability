"""Mock heat-planner-api for UI work without a deployed agent API (UI_MOCK=1 or no AGENT_API_URL).

Answers are real heat-planner-api output: docs/contracts/samples/*.json passed through the API's
_to_api_dict adapter by scripts/build_ui_samples.py into samples/. A keyword guess at the intent
picks the sample. The tract layer is still synthetic (a grid with heat placed around the sample's
sites) because the real one needs BigQuery. Every screen shows a mock banner while this is in use.
"""

import json
import math
import re
from functools import lru_cache
from pathlib import Path

from .contracts.agent_api import AgentApiResponse, TractLayer

SAMPLES = Path(__file__).parent / "samples"
OTHER_CITIES = r"\b(phoenix|dallas|houston|chicago|seattle|los angeles|new york|brooklyn|manhattan|bronx)\b"


@lru_cache(maxsize=None)
def _load(name: str) -> AgentApiResponse:
    return AgentApiResponse.model_validate(json.loads((SAMPLES / f"{name}.json").read_text(encoding="utf-8")))


def _sample() -> AgentApiResponse:
    return _load("site_selection_atlanta")


def _intent_for(msg: str) -> str:
    m = msg.lower()
    if re.search(r"\b(draft|proposal|council memo)\b", m):
        return "draft_proposal"
    if re.search(r"\bwhy not\b|\bcompare\b", m):
        return "compare_sites"
    if re.search(r"\baudit\b|\bneed (this )?most\b", m):
        return "equity_audit"
    if re.search(r"\bhow often\b|\b9[05]\s*°?f\b|\bhot days\b", m):
        return "heat_frequency"
    if re.search(r"\bwhy (is|does)\b|\btract \d{11}\b|-?\d{2}\.\d+,\s*-?\d{2}\.\d+", m):
        return "explain_location"
    return "site_selection"


# Questions with their own real sample; the rest reuse site_selection's data with a short note.
OWN_SAMPLE = {"compare_sites": "compare_site_4_atlanta", "explain_location": "explain_location_atlanta"}
NARRATIVE = {
    "draft_proposal": "The council proposal is drafted from the recommended sites and the equity audit. "
                      "Review it on the Proposal page before it goes anywhere.",
    "equity_audit": None,  # the audit's own summary
    "heat_frequency": "Atlanta's stations averaged {days} days a year at or above 95°F over 2019–2025. "
                      "Seven years show year-to-year variability, not a long-term trend.",
}


def plan(message: str, k: int | None = None) -> AgentApiResponse:
    if re.search(OTHER_CITIES, message.lower()):
        return _load("refusal_out_of_scope")
    intent_type = _intent_for(message)
    base = _load(OWN_SAMPLE.get(intent_type, "site_selection_atlanta"))
    rec = base.recommendation
    m = re.search(r"\b([1-5])\s+(?:permanent\s+)?(?:cooling\s+)?cent", message.lower())
    if k is None and m:
        k = int(m.group(1))
    if k:
        everything = rec.sites + rec.runner_up_sites
        k = max(1, min(k, len(everything) - 1))
        rec = rec.model_copy(update={"sites": everything[:k], "runner_up_sites": everything[k:]})
    intent = base.intent.model_copy(update={"intent_type": intent_type, "k": len(rec.sites)})
    narrative = base.narrative
    if intent_type in NARRATIVE:
        hf = rec.heat_frequency
        narrative = (NARRATIVE[intent_type] or (rec.equity_audit.verdict if rec.equity_audit else "") or base.narrative)
        narrative = narrative.format(days=f"{hf.mean_days_ge_95_f:.1f}" if hf and hf.mean_days_ge_95_f else "about 24")
    return base.model_copy(update={"intent": intent, "recommendation": rec, "narrative": narrative})


@lru_cache(maxsize=1)
def tract_layer() -> TractLayer:
    rec = _sample().recommendation
    sites = rec.sites + rec.runner_up_sites
    cols, rows = 16, 11
    lon0, lat0, dlon, dlat = -84.52, 33.66, 0.0165, 0.0150

    def h(a, b):
        s = math.sin(a * 12.9898 + b * 78.233) * 43758.5453
        return s - math.floor(s)

    pts = [[(lon0 + i * dlon + (0 if i in (0, cols) else (h(i, j) - .5) * dlon * .5),
             lat0 + j * dlat + (0 if j in (0, rows) else (h(j + 9, i) - .5) * dlat * .5))
            for i in range(cols + 1)] for j in range(rows + 1)]

    def near(lon, lat, scale):
        return sum(math.exp(-(((lon - s.lon) / scale) ** 2 + ((lat - s.lat) / scale) ** 2)) for s in sites)

    feats = []
    for j in range(rows):
        for i in range(cols):
            ring = [pts[j][i], pts[j][i + 1], pts[j + 1][i + 1], pts[j + 1][i], pts[j][i]]
            clon = sum(p[0] for p in ring[:4]) / 4
            clat = sum(p[1] for p in ring[:4]) / 4
            jit = h(i, j) - .5
            geo_id = f"13121{j:02d}{i:02d}00"
            heat = near(clon, clat, 0.03)
            feats.append({
                "_center": (clon, clat),
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[[round(x, 5), round(y, 5)] for x, y in ring]]},
                "properties": {
                    "geo_id": geo_id,
                    "predicted_offset_f": round(-1.6 + 2.6 * min(heat, 1.3) + jit * .7, 2),
                    "no_vehicle_rate": round(min(.6, .05 + .32 * near(clon, clat, .04) + jit * .06), 3),
                    "share_65_plus": round(max(.04, .09 + .07 * near(clon + .02, clat, .05) + jit * .04), 3),
                    "poverty_rate": round(min(.55, .08 + .25 * near(clon, clat, .04) + jit * .05), 3),
                    "population": int(1800 + h(j, i) * 4200),
                },
            })
    # Give each sample site the tract nearest to it, so sites line up with the map and scatter.
    taken = set()
    for s in sites:
        best = min((k for k in range(len(feats)) if k not in taken),
                   key=lambda k: (feats[k]["_center"][0] - s.lon) ** 2 + (feats[k]["_center"][1] - s.lat) ** 2)
        feats[best]["properties"]["geo_id"] = s.geo_id
        taken.add(best)
    for f in feats:
        del f["_center"]
    return TractLayer.model_validate({"type": "FeatureCollection", "features": feats})
