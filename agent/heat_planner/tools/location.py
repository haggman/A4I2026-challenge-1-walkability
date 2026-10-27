"""Location resolution & Google Maps URL helpers (100% US Gov Public Domain / Google Maps).

Never calls OpenStreetMap / Nominatim (ODbL is disallowed by Challenge Non-Negotiable #9).
Uses:
  1. Direct coordinate regex parsing ("33.754, -84.417")
  2. Curated Atlanta neighborhood/landmark lookup table (plus common out-of-footprint test locations)
  3. Google Maps Geocoding API (when MAPS_API_KEY is configured)
  4. US Census Bureau Public Geocoder API (geocoding.geo.census.gov — US Gov Public Domain)
Then validates Atlanta metro bounds (`33.4..34.1`, `-84.8..-84.0`) and `in_footprint` via MCP `explain_point`.
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any
from urllib.parse import quote_plus

import httpx

from ..config import Settings
from ..mcp_client import invoke_mcp_tool
from ..schemas import ToolResult

log = logging.getLogger(__name__)

_COORD_RE = re.compile(
    r"^\s*(?P<lat>[+-]?\d+(?:\.\d+)?)\s*[,\s]\s*(?P<lon>[+-]?\d+(?:\.\d+)?)\s*$"
)

# Curated Atlanta neighborhoods, landmarks, and reference tracts (WGS84)
# plus standard out-of-footprint test locations for deterministic refusal checks.
_CURATED_PLACES: dict[str, tuple[float, float, str]] = {
    # West / Southwest / South Atlanta neighborhoods
    "venetian hills": (33.7195, -84.4252, "Venetian Hills / Oakland City, Atlanta, GA"),
    "vine city": (33.7568, -84.4126, "Vine City, Atlanta, GA"),
    "english avenue": (33.7665, -84.4128, "English Avenue, Atlanta, GA"),
    "west end": (33.7397, -84.4128, "West End / Ashview Heights, Atlanta, GA"),
    "oakland city": (33.7195, -84.4252, "Venetian Hills / Oakland City, Atlanta, GA"),
    "mechanicsville": (33.7397, -84.3858, "Mechanicsville / Summerhill, Atlanta, GA"),
    "pittsburgh": (33.7285, -84.3982, "Pittsburgh, Atlanta, GA"),
    "peoplestown": (33.7295, -84.3855, "Peoplestown, Atlanta, GA"),
    "summerhill": (33.7397, -84.3858, "Mechanicsville / Summerhill, Atlanta, GA"),
    "lakewood": (33.7045, -84.3860, "Lakewood Heights, Atlanta, GA"),
    "lakewood heights": (33.7045, -84.3860, "Lakewood Heights, Atlanta, GA"),
    "sylvan hills": (33.7115, -84.4150, "Sylvan Hills, Atlanta, GA"),
    "adair park": (33.7292, -84.4105, "Adair Park, Atlanta, GA"),
    "ashview heights": (33.7397, -84.4128, "West End / Ashview Heights, Atlanta, GA"),
    "bankhead": (33.7720, -84.4290, "Bankhead, Atlanta, GA"),
    "grove park": (33.7735, -84.4475, "Grove Park, Atlanta, GA"),
    "adamsville": (33.7570, -84.5020, "Adamsville, Atlanta, GA"),
    "cascade": (33.7225, -84.4525, "Cascade / Southwest Atlanta, GA"),
    "campbellton road": (33.7172, -84.4426, "Venetian Hills / Oakland City, Atlanta, GA"),
    # Central / Midtown / Downtown / East / North Atlanta
    "downtown": (33.7550, -84.3900, "Downtown Atlanta, GA"),
    "downtown atlanta": (33.7550, -84.3900, "Downtown Atlanta, GA"),
    "five points": (33.7537, -84.3915, "Five Points, Downtown Atlanta, GA"),
    "sweet auburn": (33.7552, -84.3775, "Sweet Auburn, Atlanta, GA"),
    "old fourth ward": (33.7640, -84.3715, "Old Fourth Ward, Atlanta, GA"),
    "midtown": (33.7815, -84.3855, "Midtown Atlanta, GA"),
    "midtown atlanta": (33.7815, -84.3855, "Midtown Atlanta, GA"),
    "georgia tech": (33.7756, -84.3963, "Georgia Tech Campus, Atlanta, GA"),
    "home park": (33.7860, -84.4015, "Home Park, Atlanta, GA"),
    "atlantic station": (33.7925, -84.3965, "Atlantic Station, Atlanta, GA"),
    "grant park": (33.7375, -84.3710, "Grant Park, Atlanta, GA"),
    "inman park": (33.7610, -84.3575, "Inman Park, Atlanta, GA"),
    "little five points": (33.7650, -84.3490, "Little Five Points, Atlanta, GA"),
    "east atlanta": (33.7400, -84.3450, "East Atlanta Village, Atlanta, GA"),
    "reynoldstown": (33.7505, -84.3550, "Reynoldstown, Atlanta, GA"),
    "cabbagetown": (33.7500, -84.3645, "Cabbagetown, Atlanta, GA"),
    "edgewood": (33.7555, -84.3375, "Edgewood, Atlanta, GA"),
    "kirkwood": (33.7550, -84.3240, "Kirkwood, Atlanta, GA"),
    "piedmont park": (33.7851, -84.3738, "Piedmont Park, Atlanta, GA"),
    "buckhead": (33.8395, -84.3795, "Buckhead, Atlanta, GA"),
    "lenox": (33.8463, -84.3621, "Lenox Square / Buckhead, Atlanta, GA"),
    "morningside": (33.7960, -84.3585, "Morningside-Lenox Park, Atlanta, GA"),
    "virginia highland": (33.7815, -84.3540, "Virginia-Highland, Atlanta, GA"),
    "ansley park": (33.7945, -84.3765, "Ansley Park, Atlanta, GA"),
    "west midtown": (33.7845, -84.4140, "West Midtown, Atlanta, GA"),
    "bluff": (33.7620, -84.4130, "The Bluff (Vine City / English Ave), Atlanta, GA"),
    # Out-of-footprint locations (for deterministic refusal checks)
    "alpharetta": (34.0754, -84.2941, "Alpharetta, GA (Outside Atlanta Heat Watch Footprint)"),
    "marietta": (33.9526, -84.5499, "Marietta, GA (Outside Atlanta Heat Watch Footprint)"),
    "roswell": (34.0232, -84.3616, "Roswell, GA (Outside Atlanta Heat Watch Footprint)"),
    "peachtree city": (33.3968, -84.5963, "Peachtree City, GA (Outside Atlanta Heat Watch Footprint)"),
    "savannah": (32.0809, -81.0912, "Savannah, GA (Outside Atlanta Heat Watch Footprint)"),
    "phoenix": (33.4484, -112.0740, "Phoenix, AZ (Non-target City)"),
    "miami": (25.7617, -80.1918, "Miami, FL (Non-target City)"),
    "dallas": (32.7767, -96.7970, "Dallas, TX (Non-target City)"),
    "houston": (29.7604, -95.3698, "Houston, TX (Non-target City)"),
    "new york": (40.7128, -74.0060, "New York, NY (Non-target City)"),
    "chicago": (41.8781, -87.6298, "Chicago, IL (Non-target City)"),
}

# Tract GEOID to neighborhood label for major high-need & core Atlanta tracts
_TRACT_NEIGHBORHOODS: dict[str, str] = {
    "13121007603": "Venetian Hills / Oakland City",
    "13121004200": "West End / Ashview Heights",
    "13121004800": "Mechanicsville / Summerhill",
    "13121002600": "Vine City / English Avenue",
    "13121002500": "English Avenue / Westside",
    "13121003500": "Downtown / Five Points",
    "13121001902": "Midtown / Downtown Connector",
    "13121001002": "Home Park / Georgia Tech",
    "13121004000": "Westview / Ashview Heights",
    "13121004300": "West End",
    "13121004400": "Adair Park / Mechanicsville",
    "13121005501": "Pittsburgh",
    "13121005502": "Peoplestown / Summerhill",
    "13121005700": "Adair Park / Sylvan Hills",
    "13121006300": "Lakewood / South Atlanta",
    "13121006500": "Sylvan Hills / Perkerson",
    "13121006701": "Lakewood Heights",
    "13121007808": "Cascade / Adamsville",
    "13121008202": "Adamsville / Collier Heights",
    "13121008400": "Grove Park / Bankhead",
    "13121008500": "Bankhead / Center Hill",
    "13121008601": "Harvel Homes / West Atlanta",
    "13121011800": "Sweet Auburn / Old Fourth Ward",
    "13121012000": "West End / Mosley Park",
}


def build_google_maps_urls(lat: float, lon: float, label: str = "") -> dict[str, str]:
    """Return clickable Google Maps pin and walking-directions URLs for a coordinate."""
    coord_str = f"{lat:.5f},{lon:.5f}"
    query_param = quote_plus(f"{label} ({coord_str})" if label else coord_str)
    return {
        "google_maps_url": f"https://www.google.com/maps/search/?api=1&query={coord_str}",
        "google_maps_walking_url": (
            f"https://www.google.com/maps/dir/?api=1&destination={coord_str}&travelmode=walking"
        ),
        "location_query": query_param,
    }


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return Haversine distance in meters between two WGS84 points."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def infer_atlanta_neighborhood(
    lat: float, lon: float, geo_id: str | None = None
) -> str:
    """Return a planner-friendly Atlanta neighborhood label for (lat, lon) or geo_id."""
    if geo_id and str(geo_id).zfill(11) in _TRACT_NEIGHBORHOODS:
        return _TRACT_NEIGHBORHOODS[str(geo_id).zfill(11)]

    best_label = "Atlanta"
    best_dist_km = 999.0
    for _key, (clat, clon, label) in _CURATED_PLACES.items():
        if "Outside" in label or "Non-target" in label:
            continue
        d_km = haversine_m(lat, lon, clat, clon) / 1000.0
        if d_km < best_dist_km:
            best_dist_km = d_km
            best_label = label.replace(", Atlanta, GA", "").replace(", GA", "")
    if best_dist_km <= 3.0:
        return f"Near {best_label} (Tract {geo_id})" if geo_id else f"Near {best_label}"
    return f"Atlanta Tract {geo_id}" if geo_id else "Atlanta"


def _geocode_census(query: str) -> tuple[float, float, str] | None:
    """Geocode an address using the US Census Bureau Public Geocoder (US Gov Public Domain)."""
    addr = query.strip()
    if "ga" not in addr.lower() and "atlanta" not in addr.lower() and "," not in addr:
        addr = f"{addr}, Atlanta, GA"
    url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
    params = {
        "address": addr,
        "benchmark": "Public_AR_Current",
        "format": "json",
    }
    try:
        with httpx.Client(timeout=8.0) as http:
            resp = http.get(url, params=params)
            resp.raise_for_status()
            matches = resp.json().get("result", {}).get("addressMatches", [])
            if matches:
                top = matches[0]
                coords = top.get("coordinates", {})
                return (
                    float(coords["y"]),
                    float(coords["x"]),
                    str(top.get("matchedAddress", addr)),
                )
    except Exception as exc:
        log.warning("Census geocoder lookup failed for %r: %s", query, exc)
    return None


def _geocode_google_maps(query: str, api_key: str) -> tuple[float, float, str] | None:
    """Geocode using Google Maps Geocoding API when MAPS_API_KEY is configured."""
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": query.strip(), "key": api_key}
    try:
        with httpx.Client(timeout=8.0) as http:
            resp = http.get(url, params=params)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                top = results[0]
                loc = top["geometry"]["location"]
                return (
                    float(loc["lat"]),
                    float(loc["lng"]),
                    str(top.get("formatted_address", query)),
                )
    except Exception as exc:
        log.warning("Google Maps geocoder lookup failed for %r: %s", query, exc)
    return None


def resolve_location(query: str) -> dict[str, Any]:
    """Resolve a coordinate string, Atlanta neighborhood, or street address to (lat, lon)
    and verify whether it lies inside the Atlanta Heat Watch campaign footprint.

    Args:
        query: A coordinate pair ("33.754, -84.417"), an Atlanta neighborhood or landmark
            ("Venetian Hills", "Vine City", "West End", "Midtown"), or a street address.
    """
    s = Settings()
    raw = (query or "").strip()
    if not raw:
        return ToolResult(
            status="not_found",
            error_message="Empty location query provided.",
        ).model_dump()

    lat: float | None = None
    lon: float | None = None
    formatted_address: str = raw
    resolution_source: str = "coordinates"

    # 1. Coordinate pair ("33.754, -84.417")
    m = _COORD_RE.match(raw)
    if m:
        lat = float(m.group("lat"))
        lon = float(m.group("lon"))
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return ToolResult(
                status="not_found",
                error_message=f"Coordinates ({lat}, {lon}) are outside valid WGS84 bounds.",
            ).model_dump()
        formatted_address = f"({lat:.5f}, {lon:.5f})"

    # 2. Curated neighborhood / landmark / city lookup
    if lat is None:
        cleaned = (
            raw.lower()
            .replace(", atlanta, ga", "")
            .replace(", atlanta", "")
            .replace(" atlanta, ga", "")
            .replace(" atlanta", "")
            .replace(", ga", "")
            .strip()
        )
        if cleaned in _CURATED_PLACES:
            lat, lon, formatted_address = _CURATED_PLACES[cleaned]
            resolution_source = "atlanta_curated_gazetteer"
        else:
            for key, (clat, clon, label) in _CURATED_PLACES.items():
                if key in cleaned:
                    lat, lon, formatted_address = clat, clon, label
                    resolution_source = "atlanta_curated_gazetteer"
                    break

    # 3. Google Maps Geocoding API (if MAPS_API_KEY is configured)
    if lat is None and s.maps_api_key:
        g_res = _geocode_google_maps(raw, s.maps_api_key)
        if g_res:
            lat, lon, formatted_address = g_res
            resolution_source = "google_maps_geocoder"

    # 4. US Census Bureau Public Geocoder (US Federal Government Public Domain)
    if lat is None:
        c_res = _geocode_census(raw)
        if c_res:
            lat, lon, formatted_address = c_res
            resolution_source = "us_census_bureau_geocoder"

    if lat is None or lon is None:
        return ToolResult(
            status="not_found",
            error_message=(
                f"Could not resolve '{raw}' to coordinates. Try providing decimal "
                f"coordinates (e.g., '33.7568, -84.4126') or a street address in {s.city}, GA."
            ),
        ).model_dump()

    # 5. Fast Atlanta metro bounding-box check (`33.4..34.1`, `-84.8..-84.0`)
    urls = build_google_maps_urls(lat, lon, formatted_address)
    if not (s.lat_min <= lat <= s.lat_max and s.lon_min <= lon <= s.lon_max):
        payload = {
            "query": raw,
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "formatted_address": formatted_address,
            "neighborhood": formatted_address,
            "geo_id": None,
            "in_footprint": False,
            "km_from_center": None,
            "resolution_source": resolution_source,
            **urls,
        }
        return ToolResult(
            status="out_of_scope",
            data=payload,
            error_message=(
                f"'{formatted_address}' ({lat:.4f}, {lon:.4f}) is outside {s.city}, GA. "
                f"Our BigQuery ML model ({s.bqml_model_id}) is trained exclusively on {s.city}'s "
                "Heat Watch campaign footprint and refuses to extrapolate to other cities."
            ),
            model_version=s.bqml_model_id,
        ).model_dump()

    # 6. Check whether (lat, lon) lies inside the Atlanta Heat Watch campaign footprint via MCP explain_point
    try:
        rows, prov = invoke_mcp_tool(
            "explain_point",
            tool_name="resolve_location",
            lat=float(lat),
            lon=float(lon),
        )
    except Exception as exc:
        log.exception("explain_point footprint check failed")
        return ToolResult(status="error", error_message=str(exc)).model_dump()

    fp_row = rows[0] if rows else {}
    in_footprint = bool(fp_row.get("in_footprint", False))
    geo_id = fp_row.get("geo_id")
    km_from_center = fp_row.get("km_from_center")
    neighborhood = (
        infer_atlanta_neighborhood(lat, lon, geo_id) if in_footprint else formatted_address
    )
    urls = build_google_maps_urls(lat, lon, neighborhood)

    payload = {
        "query": raw,
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "formatted_address": formatted_address,
        "neighborhood": neighborhood,
        "geo_id": geo_id,
        "in_footprint": in_footprint,
        "km_from_center": km_from_center,
        "resolution_source": resolution_source,
        **urls,
    }

    if not in_footprint:
        return ToolResult(
            status="out_of_scope",
            data=payload,
            error_message=(
                f"'{formatted_address}' ({lat:.4f}, {lon:.4f}) is outside the {s.city} Heat Watch "
                f"campaign footprint ({km_from_center} km from the campaign centroid). "
                f"Our BigQuery ML model ({s.bqml_model_id}) is trained exclusively on {s.city}'s "
                "Heat Watch campaign footprint and cannot extrapolate outside it."
            ),
            provenance=[prov],
            model_version=s.bqml_model_id,
        ).model_dump()

    return ToolResult(
        status="success",
        data=payload,
        provenance=[prov],
        model_version=s.bqml_model_id,
    ).model_dump()


def resolve_atlanta_location(query: str) -> dict[str, Any]:
    """Alias for resolve_location."""
    return resolve_location(query)

