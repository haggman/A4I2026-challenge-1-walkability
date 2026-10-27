"""Stage 3 VizSpecBuilder: AgentApiResponse (+ tract layer) -> VizSpec, deterministically.

No model calls and no data access here: everything comes from the agent API's verified
response. Numbers are only reformatted, never derived beyond simple sums, ratios and ranks.

Tract polygons are served once through /api/tracts instead of in every VizSpec, so
map_geojson carries only sites and catchments. The tract layer is still used here for the
audit scatter.
"""

import math
from statistics import median

from .contracts.agent_api import (AgentApiResponse, EquityAudit, PlacementRecommendation,
                                  SiteAssessment, TractLayer)
from .contracts.viz_spec import (AuditComparisonRow, AuditScatter, AuditSummary, ChecklistItem,
                                 CompareBar, DriverBar, GeoJSONFeatureCollection, MapFeature,
                                 MapFeatureProperties, ProposalDoc, ProposalSiteRow,
                                 RankedSiteRow, ScatterPoint, SiteComparison, SiteDetail,
                                 SiteDriverBars, VizSpec)

PRIMARY_VIEW = {
    "site_selection": "map_and_table",
    "demographics": "map_and_table",
    "generic_data": "map_and_table",
    "explain_location": "driver_breakdown",
    "compare_sites": "comparison_view",
    "heat_frequency": "hot_days_chart",
    "equity_audit": "equity_audit_table",
    "draft_proposal": "proposal_document",
}

AUDIT_LABELS = {
    "median_income": ("Median household income", False),
    "poverty_rate": ("Poverty rate", True),
    "no_vehicle_rate": ("Households without a car", True),
    "share_65_plus": ("Residents 65 and older", True),
}

DEFAULT_RADIUS_M = 800.0
NUMBER_WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five"}
MAP_RUNNER_UPS = 2  # passed-over pins on the map; the ranked table keeps them all


# ------------------------------------------------------------------ formatting

def signed_f(v: float) -> str:
    return f"{'+' if v >= 0 else '−'}{abs(v):.2f}°F"


def pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.1f}%"


def money(v: float) -> str:
    return f"${v:,.0f}"


def site_name(s: SiteAssessment) -> str:
    return s.address_hint or f"Tract {s.geo_id}"


def maps_urls(lat: float, lon: float) -> tuple[str, str]:
    q = f"{lat:.5f},{lon:.5f}"
    return (f"https://www.google.com/maps/search/?api=1&query={q}",
            f"https://www.google.com/maps/dir/?api=1&destination={q}&travelmode=walking")


def circle(lat: float, lon: float, radius_m: float, n: int = 48) -> dict:
    """Straight-line reach as a GeoJSON polygon (good enough at city scale)."""
    dlat = radius_m / 111_320
    dlon = dlat / math.cos(math.radians(lat))
    ring = [[round(lon + dlon * math.cos(2 * math.pi * i / n), 6),
             round(lat + dlat * math.sin(2 * math.pi * i / n), 6)] for i in range(n)]
    return {"type": "Polygon", "coordinates": [ring + [ring[0]]]}


# ------------------------------------------------------------------ pieces

def _radius(s: SiteAssessment, fallback: float) -> float:
    return s.catchment.radius_m if s.catchment else fallback


def build_map(rec: PlacementRecommendation, radius_m: float) -> GeoJSONFeatureCollection:
    feats = []
    shown = [(s, "recommended_site") for s in rec.sites] + [(s, "runner_up_site") for s in rec.runner_up_sites[:MAP_RUNNER_UPS]]
    for s, kind in shown:
        props = dict(rank=s.rank, geo_id=s.geo_id, label=site_name(s),
                     predicted_offset_f=s.predicted_offset_f, unmeasured=s.unmeasured)
        feats.append(MapFeature(geometry={"type": "Point", "coordinates": [s.lon, s.lat]},
                                properties=MapFeatureProperties(feature_type=kind, **props)))
        if kind == "recommended_site":
            r = _radius(s, radius_m)
            feats.append(MapFeature(geometry=circle(s.lat, s.lon, r),
                                    properties=MapFeatureProperties(feature_type="catchment", rank=s.rank, radius_m=r)))
    return GeoJSONFeatureCollection(features=feats)


def build_ranked_table(rec: PlacementRecommendation) -> list[RankedSiteRow]:
    rows = []
    for s, funded in [(s, True) for s in rec.sites] + [(s, False) for s in rec.runner_up_sites]:
        rows.append(RankedSiteRow(
            rank=s.rank, neighborhood=s.address_hint, geo_id=s.geo_id,
            predicted_offset_f=s.predicted_offset_f, unmeasured=s.unmeasured,
            no_vehicle_rate=s.tract_no_vehicle_rate, share_65_plus=s.tract_share_65_plus,
            poverty_rate=s.tract_poverty_rate, priority_score=s.priority_score,
            lat=s.lat, lon=s.lon,
            residents_reached=s.catchment.population_within_radius if s.catchment else None,
            hot_days_ge_95=s.hot_days.mean_days_ge_95f_equiv_per_yr if s.hot_days else None,
            funded=funded, passed_over_reason=s.passed_over_reason))
    return rows


def dominant(s: SiteAssessment):
    adds = [d for d in s.drivers if d.attribution_f > 0]
    return max(adds, key=lambda d: d.attribution_f) if adds else None


def build_driver_bars(rec: PlacementRecommendation) -> list[SiteDriverBars]:
    out = []
    for s in rec.sites + rec.runner_up_sites:
        bars = [DriverBar(label=d.label, attribution_f=d.attribution_f,
                          effect="adds_heat" if d.attribution_f >= 0 else "reduces_heat")
                for d in sorted(s.drivers, key=lambda d: -abs(d.attribution_f))]
        top = dominant(s)
        out.append(SiteDriverBars(rank=s.rank, bars=bars, site_offset_f=s.predicted_offset_f,
                                  dominant_driver=top.label if top else None))
    return out


def _city_value(audit: EquityAudit | None, measure: str) -> float | None:
    if not audit:
        return None
    return next((m.city_value for m in audit.measures if m.measure == measure), None)


def build_site_details(rec: PlacementRecommendation, radius_m: float) -> list[SiteDetail]:
    audit = rec.equity_audit
    out = []
    for s in rec.sites:
        bars = []
        for label, site_v, measure in (("Households without a car", s.tract_no_vehicle_rate, "no_vehicle_rate"),
                                       ("Residents 65 and older", s.tract_share_65_plus, "share_65_plus")):
            city_v = _city_value(audit, measure)
            if site_v is not None and city_v is not None:
                bars.append(CompareBar(label=label, site_value=site_v, city_value=city_v))
        top = dominant(s)
        diagnosis = (f"{top.label} adds the most heat here ({signed_f(top.attribution_f)} of "
                     f"{signed_f(s.predicted_offset_f)}). We can diagnose the cause; we can't simulate the fix."
                     if top else None)
        maps, walk = maps_urls(s.lat, s.lon)
        out.append(SiteDetail(
            rank=s.rank, title=f"Site {s.rank} · {site_name(s)}", lat=s.lat, lon=s.lon, geo_id=s.geo_id,
            hot_days_ge_95=s.hot_days.mean_days_ge_95f_equiv_per_yr if s.hot_days else None,
            city_hot_days_ge_95=s.hot_days.city_baseline_days_ge_95f_per_yr if s.hot_days else None,
            residents_nearby=s.catchment.population_within_radius if s.catchment else None,
            radius_m=_radius(s, radius_m), who_lives_here=bars, diagnosis=diagnosis,
            maps_url=maps, walking_url=walk))
    return out


def build_comparison(rec: PlacementRecommendation) -> SiteComparison | None:
    if not rec.sites or not rec.runner_up_sites:
        return None
    a, b = rec.sites[-1], rec.runner_up_sites[0]

    def row(label, va, vb, fmt):
        delta = None if va is None or vb is None else vb - va
        return {"label": label, "funded": fmt(va) if va is not None else "—",
                "runner_up": fmt(vb) if vb is not None else "—",
                "delta": None if delta is None else fmt(delta) if fmt is not pct else f"{delta * 100:+.1f} pts"}

    rows = [
        row("Heat offset", a.predicted_offset_f, b.predicted_offset_f, signed_f),
        row("Households without a car", a.tract_no_vehicle_rate, b.tract_no_vehicle_rate, pct),
        row("Residents 65+", a.tract_share_65_plus, b.tract_share_65_plus, pct),
        row("Poverty rate", a.tract_poverty_rate, b.tract_poverty_rate, pct),
        row("Priority score", a.priority_score, b.priority_score, lambda v: f"{v:.2f}"),
    ]
    return SiteComparison(funded_rank=a.rank, runner_up_rank=b.rank, rows=rows, reason=b.passed_over_reason)


def build_audit(audit: EquityAudit) -> tuple[list[AuditComparisonRow], AuditSummary]:
    rows = []
    for m in audit.measures:
        label, higher_is_need = AUDIT_LABELS[m.measure]
        fmt = money if m.measure == "median_income" else pct
        rows.append(AuditComparisonRow(
            measure=m.measure, label=label, sites_value=m.sites_value, city_value=m.city_value,
            ratio=m.ratio, higher_means_need=higher_is_need,
            toward_need=(m.ratio > 1) if higher_is_need else (m.ratio < 1),
            display_sites=fmt(m.sites_value), display_city=fmt(m.city_value)))
    n = sum(1 for r in rows if r.toward_need)
    headline = (f"Our sites skew toward need on {f'all {n}' if n == len(rows) else f'{n} of {len(rows)}'} measures."
                if n * 2 > len(rows) else "Our sites don't clearly skew toward need.")
    short = audit.verdict and len(audit.verdict) <= 90
    return rows, AuditSummary(measures_toward_need=n, measures_total=len(rows),
                              verdict=audit.verdict if short else headline,
                              detail=None if short else audit.verdict)


def _pct_rank(values: list[float]) -> dict[int, float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    return {i: (pos / (len(values) - 1) if len(values) > 1 else 0.5) for pos, i in enumerate(order)}


def build_scatter(rec: PlacementRecommendation, tracts: TractLayer) -> AuditScatter | None:
    rows = [f.properties for f in tracts.features
            if f.properties.predicted_offset_f is not None and f.properties.no_vehicle_rate is not None
            and f.properties.share_65_plus is not None]
    if len(rows) < 3:
        return None
    car = _pct_rank([r.no_vehicle_rate for r in rows])
    age = _pct_rank([r.share_65_plus for r in rows])
    ranks = {s.geo_id: (s.rank, True) for s in rec.sites}
    ranks.update({s.geo_id: (s.rank, False) for s in rec.runner_up_sites[:MAP_RUNNER_UPS] if s.geo_id not in ranks})
    pts = []
    for i, r in enumerate(rows):
        rank, funded = ranks.get(r.geo_id, (None, None))
        pts.append(ScatterPoint(geo_id=r.geo_id, predicted_offset_f=r.predicted_offset_f,
                                vulnerability=round((car[i] + age[i]) / 2, 4), site_rank=rank, funded=funded))
    return AuditScatter(points=pts,
                        offset_split_f=median(p.predicted_offset_f for p in pts),
                        vulnerability_split=median(p.vulnerability for p in pts),
                        note="Vulnerability = average of each tract's no-car and 65+ percentile. Lines are city medians.")


def hot_days_chart(rec: PlacementRecommendation) -> dict | None:
    hf = rec.heat_frequency
    if not hf or not hf.years:
        return None
    values = [{"year": y.year, "threshold": t, "days": getattr(y, k)}
              for y in hf.years for t, k in (("≥90°F", "days_ge_90_f"), ("≥95°F", "days_ge_95_f"), ("≥100°F", "days_ge_100_f"))]
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": "Days per year at or above each threshold, Atlanta GHCN stations",
        "data": {"values": values},
        "mark": "bar",
        "encoding": {
            "x": {"field": "year", "type": "ordinal", "title": None},
            "xOffset": {"field": "threshold"},
            "y": {"field": "days", "type": "quantitative", "title": "Days"},
            "color": {"field": "threshold", "type": "nominal", "title": None},
        },
    }


def _span(vals: list[float], fmt) -> str:
    lo, hi = min(vals), max(vals)
    return fmt(lo) if round(lo, 2) == round(hi, 2) else f"{fmt(lo)}–{fmt(hi)}"


def build_proposal(resp: AgentApiResponse, rec: PlacementRecommendation,
                   audit_rows: list[AuditComparisonRow], radius_m: float) -> ProposalDoc:
    sites = rec.sites
    names = [f"Site {s.rank} ({site_name(s)})" for s in sites]
    listed = ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1] if names else "[sites]"
    catch = [s.catchment for s in sites if s.catchment]
    days = [s.hot_days.mean_days_ge_95f_equiv_per_yr for s in sites if s.hot_days]
    parts = [f"We recommend permanent cooling centers at {listed}."]
    if catch and len(catch) == len(sites):
        parts.append(
            f"Together they place relief within {radius_m:,.0f} m (straight-line) of "
            f"{sum(c.population_within_radius for c in catch):,} residents, including "
            f"{sum(c.pop_65_plus_within_radius for c in catch):,} aged 65 and older and "
            f"{sum(c.car_free_households_within_radius for c in catch):,} households without a car.")
    if sites:
        offs = [s.predicted_offset_f for s in sites]
        run = (f"{_span(offs, lambda v: f'{v:.2f}')}°F hotter than" if min(offs) >= 0
               else f"{_span(offs, signed_f)} relative to")
        clause = f"The sites run {run} {rec.city}'s average on the campaign day"
        clause += (f" and see roughly {_span(days, lambda v: f'{v:.0f}')} days a year at or above 95°F-equivalent heat."
                   if days and len(days) == len(sites) else ".")
        parts.append(clause)

    rows = []
    for s in sites:
        c = s.catchment
        nearby = (f"{c.population_within_radius:,} (no car {pct(c.no_vehicle_rate_within_radius)} · "
                  f"65+ {pct(c.share_65_plus_within_radius)})") if c else "—"
        rows.append(ProposalSiteRow(rank=s.rank, name=site_name(s), location=f"{s.lat:.4f}, {s.lon:.4f}",
                                    offset=signed_f(s.predicted_offset_f),
                                    hot_days_ge_95=f"{s.hot_days.mean_days_ge_95f_equiv_per_yr:.0f}" if s.hot_days else "—",
                                    nearby=nearby))

    equity = None
    if audit_rows:
        bits = [f"{r.ratio:.2f}× the city's {r.label.lower()}" for r in audit_rows]
        equity = "Compared with the Atlanta average, the recommended tracts have " + "; ".join(bits) + "."

    sections = rec.proposal_sections
    checklist = [
        ChecklistItem(label="Every site has coordinates", done=all(s.lat and s.lon for s in sites)),
        ChecklistItem(label="Every claim cites a source", done=bool(resp.citations) and resp.verification.passed),
        ChecklistItem(label="What it displaces is stated", done=bool(sections.get("what_this_displaces"))),
        ChecklistItem(label="Equity audit attached", done=bool(audit_rows)),
        ChecklistItem(label="Limits stated plainly", done=bool(rec.limitations)),
        ChecklistItem(label="Costs confirmed by finance", done=False),
    ]
    checklist = [c.model_copy(update={"note": "done" if c.done else "needs a person"}) for c in checklist]
    v = resp.verification
    status = ("Draft ready · every claim sourced · review before sending" if v.passed and not v.fallback_used
              else "Draft from a template: the writer's text didn't pass the number check · review before sending")
    count = NUMBER_WORDS.get(len(sites), str(len(sites)))
    return ProposalDoc(
        title=f"{count} permanent cooling center{'s' if len(sites) != 1 else ''}, sited where heat hurts most",
        recommendation=" ".join(parts), sites=rows,
        why_these=sections.get("why_these"), what_this_displaces=sections.get("what_this_displaces"),
        equity_check=equity, limitations=list(rec.limitations),
        source_badges=["BQML", "Station history", "ACS", "EXPLAIN_PREDICT"],
        checklist=checklist, status_line=status)


# ------------------------------------------------------------------ entry point

def build_viz_spec(resp: AgentApiResponse, tracts: TractLayer | None = None, mock: bool = False) -> VizSpec:
    rec = resp.recommendation
    if resp.status != "ok" or rec is None:
        return VizSpec(primary_view="empty", mock=mock)
    radius_m = resp.intent.radius_m or DEFAULT_RADIUS_M
    audit_rows, summary = build_audit(rec.equity_audit) if rec.equity_audit else ([], None)
    return VizSpec(
        primary_view=PRIMARY_VIEW.get(resp.intent.intent_type, "map_and_table"),
        map_geojson=build_map(rec, radius_m),
        ranked_table=build_ranked_table(rec),
        driver_bars=build_driver_bars(rec),
        vega_lite_spec=hot_days_chart(rec),
        audit_table=audit_rows,
        site_details=build_site_details(rec, radius_m),
        comparison=build_comparison(rec),
        audit_summary=summary,
        audit_scatter=build_scatter(rec, tracts) if tracts else None,
        racial_composition=list(rec.equity_audit.racial_composition) if rec.equity_audit else [],
        proposal=build_proposal(resp, rec, audit_rows, radius_m),
        limitations=list(rec.limitations),
        mock=mock,
    )
