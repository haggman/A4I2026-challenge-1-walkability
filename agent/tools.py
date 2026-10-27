"""BigQuery, BigQuery ML, and Google Maps tools for Urban Heat Resilience Assistant."""

import os
import urllib.parse
import urllib.request
import json
from typing import Any, Dict, List, Optional
from google.cloud import bigquery

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-04-ec3596addc43")
DATASET_ID = "a4i_climate"
MODEL_ID = f"{PROJECT_ID}.{DATASET_ID}.heat_offset_model"

bq_client = bigquery.Client(project=PROJECT_ID)

_CITY_CENTROID = None


def get_city_centroid():
    global _CITY_CENTROID
    if _CITY_CENTROID is None:
        query = f"""
        SELECT
          ROUND(AVG(latitude), 4) AS lat,
          ROUND(AVG(longitude), 4) AS lon,
          ROUND(AVG(temp_f), 1) AS mean_temp
        FROM `{PROJECT_ID}.{DATASET_ID}.heat_observations`
        """
        results = bq_client.query(query).result()
        row = next(iter(results), None)
        if row:
            _CITY_CENTROID = {
                "lat": float(row.lat),
                "lon": float(row.lon),
                "mean_temp": float(row.mean_temp),
            }
        else:
            _CITY_CENTROID = {"lat": 33.79, "lon": -84.4057, "mean_temp": 82.0}
    return _CITY_CENTROID


def build_google_maps_urls(latitude: float, longitude: float, label: Optional[str] = None) -> Dict[str, str]:
    """Builds universal Google Maps links for viewing, directions, and satellite exploration."""
    lat_str = f"{latitude:.4f}"
    lon_str = f"{longitude:.4f}"
    coords = f"{lat_str},{lon_str}"
    query = urllib.parse.quote(label if label else coords)
    
    return {
        "maps_view_url": f"https://www.google.com/maps/search/?api=1&query={query}",
        "maps_walking_directions_url": f"https://www.google.com/maps/dir/?api=1&destination={urllib.parse.quote(coords)}&travelmode=walking",
        "maps_satellite_url": f"https://www.google.com/maps/@{coords},16z/data=!3m1!1e3",
    }


def geocode_address(address_or_intersection: str) -> Dict[str, Any]:
    """Geocodes a street name, address, or landmark to geographic coordinates (latitude, longitude).

    Allows municipal planners to query by street name (e.g. '10th St NE, Atlanta' or 'Elm St, Dallas')
    instead of requiring raw coordinates.

    Args:
        address_or_intersection: The human-readable address, intersection, or landmark name.

    Returns:
        Dictionary containing resolved latitude, longitude, formatted address, and Google Maps URLs.
    """
    try:
        q = urllib.parse.quote(address_or_intersection)
        url = f"https://nominatim.openstreetmap.org/search?format=jsonv2&q={q}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AgentsForImpact-UrbanHeatPlanner/1.0 (Climate Resilient Cities)"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if not data:
            return {
                "error": f"Could not find coordinates for '{address_or_intersection}'. Please provide a nearby major cross street or city name."
            }

        first_hit = data[0]
        lat = round(float(first_hit["lat"]), 4)
        lon = round(float(first_hit["lon"]), 4)
        maps_links = build_google_maps_urls(lat, lon, label=first_hit.get("display_name"))

        return {
            "query": address_or_intersection,
            "latitude": lat,
            "longitude": lon,
            "resolved_name": first_hit.get("display_name"),
            **maps_links
        }
    except Exception as e:
        return {"error": f"Geocoding service unavailable: {str(e)}"}


def reverse_geocode_location(latitude: float, longitude: float) -> Dict[str, Any]:
    """Resolves coordinates into human-readable street address, neighborhood, and Google Maps links.

    Args:
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.

    Returns:
        Dictionary containing street name, neighborhood, city, and Google Maps URLs.
    """
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={latitude:.4f}&lon={longitude:.4f}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AgentsForImpact-UrbanHeatPlanner/1.0 (Climate Resilient Cities)"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        addr = data.get("address", {})
        street = addr.get("road") or addr.get("pedestrian") or "Unknown Street"
        neighborhood = addr.get("neighbourhood") or addr.get("suburb") or addr.get("quarter") or "Urban Core"
        city = addr.get("city") or addr.get("town") or addr.get("county") or "Metro Area"

        maps_links = build_google_maps_urls(latitude, longitude, label=data.get("display_name"))

        return {
            "latitude": latitude,
            "longitude": longitude,
            "street": street,
            "neighborhood": neighborhood,
            "city": city,
            "full_address": data.get("display_name"),
            **maps_links
        }
    except Exception as e:
        maps_links = build_google_maps_urls(latitude, longitude)
        return {
            "latitude": latitude,
            "longitude": longitude,
            "street": "Coordinates Centroid",
            "neighborhood": "Urban District",
            **maps_links
        }


def predict_heat_offset(
    latitude: float,
    longitude: float,
) -> Dict[str, Any]:
    """Predicts microclimate heat offset (degrees F relative to city baseline) using BigQuery ML.

    Also returns top explainability feature attributions via ML.EXPLAIN_PREDICT and Google Maps links.

    Args:
        latitude: Latitude of candidate location.
        longitude: Longitude of candidate location.

    Returns:
        Dictionary containing predicted_offset_f, qualitative_risk, attributions, and Google Maps URLs.
    """
    centroid = get_city_centroid()
    northing_km = (latitude - centroid["lat"]) * 111.0
    easting_km = (longitude - centroid["lon"]) * 93.0

    query = f"""
    SELECT
      predicted_temp_offset_f,
      ARRAY(
        SELECT AS STRUCT feature, attribution
        FROM UNNEST(top_feature_attributions)
        ORDER BY ABS(attribution) DESC
        LIMIT 3
      ) AS top_attributions
    FROM ML.EXPLAIN_PREDICT(
      MODEL `{MODEL_ID}`,
      (
        SELECT
          @lat AS latitude,
          @lon AS longitude,
          @northing AS northing_km,
          @easting AS easting_km
      ),
      STRUCT(3 AS top_k_features)
    )
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("lat", "FLOAT64", latitude),
            bigquery.ScalarQueryParameter("lon", "FLOAT64", longitude),
            bigquery.ScalarQueryParameter("northing", "FLOAT64", northing_km),
            bigquery.ScalarQueryParameter("easting", "FLOAT64", easting_km),
        ]
    )

    try:
        results = bq_client.query(query, job_config=job_config).result()
        row = next(iter(results), None)
        if not row:
            return {"error": "No prediction generated for the given coordinates."}

        pred_offset = round(float(row.predicted_temp_offset_f), 2)
        attributions = [
            {"feature": attr["feature"], "attribution": round(float(attr["attribution"]), 3)}
            for attr in row.top_attributions
        ]

        if pred_offset >= 2.0:
            risk = "Severe Urban Heat Island"
        elif pred_offset >= 0.5:
            risk = "Elevated Heat Exposure"
        elif pred_offset >= -0.5:
            risk = "Moderate / City Baseline"
        else:
            risk = "Cool Microclimate / Buffered"

        geo_info = reverse_geocode_location(latitude, longitude)

        return {
            "latitude": latitude,
            "longitude": longitude,
            "neighborhood": geo_info.get("neighborhood"),
            "street": geo_info.get("street"),
            "predicted_temp_offset_f": pred_offset,
            "interpretation": f"This location runs {abs(pred_offset)}°F {'warmer' if pred_offset >= 0 else 'cooler'} than the city baseline.",
            "heat_risk_level": risk,
            "feature_attributions": attributions,
            "google_maps_url": geo_info.get("maps_view_url"),
            "walking_route_url": geo_info.get("maps_walking_directions_url"),
        }
    except Exception as e:
        return {"error": f"Failed to predict heat offset: {str(e)}"}


def rank_candidate_sites(limit: int = 5) -> List[Dict[str, Any]]:
    """Ranks high-vulnerability candidate locations across the city for cooling center placement.

    Combines predicted heat offset from BigQuery ML with Census demographic indicators
    (no-vehicle rate, poverty rate, elderly population) and attaches Google Maps navigation links.

    Args:
        limit: Number of top candidate sites to return (default: 5, max 10).

    Returns:
        List of ranked candidate sites with coordinates, predicted offset, vulnerability metrics, and Google Maps links.
    """
    max_limit = min(max(1, limit), 10)
    centroid = get_city_centroid()

    query = f"""
    WITH candidate_tracts AS (
      SELECT
        d.geo_id,
        d.tract_lat AS latitude,
        d.tract_lon AS longitude,
        d.total_pop,
        d.median_age,
        d.median_income,
        d.poverty_rate,
        d.no_vehicle_rate,
        (d.tract_lat - {centroid['lat']}) * 111.0 AS northing_km,
        (d.tract_lon - ({centroid['lon']})) * 93.0 AS easting_km
      FROM `{PROJECT_ID}.{DATASET_ID}.tract_demographics` d
      WHERE d.total_pop > 1000
        AND d.tract_lat IS NOT NULL
        AND d.tract_lon IS NOT NULL
    ),
    scored AS (
      SELECT
        c.*,
        p.predicted_temp_offset_f,
        p.top_feature_attributions
      FROM ML.EXPLAIN_PREDICT(
        MODEL `{MODEL_ID}`,
        (SELECT latitude, longitude, northing_km, easting_km FROM candidate_tracts),
        STRUCT(3 AS top_k_features)
      ) p
      JOIN candidate_tracts c
        ON p.latitude = c.latitude AND p.longitude = c.longitude
    )
    SELECT
      geo_id,
      ROUND(latitude, 4) AS latitude,
      ROUND(longitude, 4) AS longitude,
      total_pop,
      median_age,
      ROUND(CASE WHEN median_income > 0 THEN median_income END, 0) AS median_income,
      ROUND(poverty_rate * 100, 1) AS poverty_rate_pct,
      ROUND(no_vehicle_rate * 100, 1) AS no_vehicle_rate_pct,
      ROUND(predicted_temp_offset_f, 2) AS predicted_temp_offset_f,
      ROUND(
        (predicted_temp_offset_f + 3.0) * 1.5 +
        (no_vehicle_rate * 100 * 0.4) +
        (poverty_rate * 100 * 0.3) +
        (CASE WHEN median_age > 40 THEN 5 ELSE 0 END),
        2
      ) AS composite_vulnerability_score,
      ARRAY(
        SELECT AS STRUCT feature, ROUND(attribution, 3) AS attribution
        FROM UNNEST(top_feature_attributions)
        ORDER BY ABS(attribution) DESC
        LIMIT 2
      ) AS key_drivers
    FROM scored
    ORDER BY composite_vulnerability_score DESC
    LIMIT {max_limit}
    """

    try:
        results = bq_client.query(query).result()
        sites = []
        for rank, row in enumerate(results, 1):
            drivers = [
                f"{attr['feature']} ({attr['attribution']:+.2f}°F)"
                for attr in row.key_drivers
            ]
            maps_info = build_google_maps_urls(row.latitude, row.longitude)
            sites.append({
                "rank": rank,
                "census_tract": row.geo_id,
                "coordinates": {"latitude": row.latitude, "longitude": row.longitude},
                "predicted_temp_offset_f": row.predicted_temp_offset_f,
                "composite_vulnerability_score": row.composite_vulnerability_score,
                "population": int(row.total_pop) if row.total_pop else None,
                "median_age": row.median_age,
                "median_income": row.median_income,
                "poverty_rate_pct": row.poverty_rate_pct,
                "no_vehicle_rate_pct": row.no_vehicle_rate_pct,
                "key_heat_drivers": drivers,
                "google_maps_link": maps_info["maps_view_url"],
                "walking_directions_link": maps_info["maps_walking_directions_url"],
            })
        return sites
    except Exception as e:
        return [{"error": f"Failed to rank candidate sites: {str(e)}"}]


def analyze_heat_frequency(temp_threshold_f: float = 95.0) -> Dict[str, Any]:
    """Analyzes 7-year historical weather station data (GHCN-Daily) for extreme heat frequency.

    Args:
        temp_threshold_f: High temperature threshold in Fahrenheit (default: 95.0).

    Returns:
        Summary of historical extreme heat days per year and trend indicators.
    """
    query = f"""
    SELECT
      EXTRACT(YEAR FROM observation_date) AS year,
      COUNT(DISTINCT observation_date) AS days_recorded,
      COUNTIF(max_temp_f >= @threshold) AS days_above_threshold,
      ROUND(MAX(max_temp_f), 1) AS record_high_temp_f,
      ROUND(AVG(max_temp_f), 1) AS avg_summer_max_f
    FROM `{PROJECT_ID}.{DATASET_ID}.station_daily_temps`
    WHERE max_temp_f IS NOT NULL
      AND EXTRACT(MONTH FROM observation_date) IN (6, 7, 8, 9)
    GROUP BY year
    ORDER BY year ASC
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("threshold", "FLOAT64", temp_threshold_f)
        ]
    )

    try:
        results = bq_client.query(query, job_config=job_config).result()
        yearly_stats = []
        for row in results:
            yearly_stats.append({
                "year": row.year,
                "days_above_threshold": row.days_above_threshold,
                "record_high_f": row.record_high_temp_f,
                "summer_avg_high_f": row.avg_summer_max_f,
            })

        if not yearly_stats:
            return {"error": "No station daily temperature history available."}

        avg_days = round(sum(y["days_above_threshold"] for y in yearly_stats) / len(yearly_stats), 1)
        max_year = max(yearly_stats, key=lambda x: x["days_above_threshold"])

        return {
            "threshold_f": temp_threshold_f,
            "average_annual_days_above_threshold": avg_days,
            "worst_year_on_record": {
                "year": max_year["year"],
                "days_above_threshold": max_year["days_above_threshold"],
                "record_high_f": max_year["record_high_f"]
            },
            "yearly_breakdown": yearly_stats,
            "resilience_implication": (
                f"The city averages {avg_days} station-days above {temp_threshold_f}°F each summer. "
                f"Locations with positive heat offsets experience this dangerous threshold far more frequently."
            )
        }
    except Exception as e:
        return {"error": f"Failed to analyze heat frequency: {str(e)}"}


def audit_equity(candidate_geo_ids: List[str]) -> Dict[str, Any]:
    """Audits recommended sites against city-wide demographic baselines.

    Verifies whether recommendations reach the most vulnerable communities
    (poverty, no-car access, elderly) rather than affluent or low-need areas.

    Args:
        candidate_geo_ids: List of 11-digit Census tract GEOIDs for recommended sites.

    Returns:
        Comparative audit metrics between recommended tracts and overall city averages.
    """
    if not candidate_geo_ids:
        return {"error": "Please provide at least one tract geo_id to audit."}

    formatted_ids = ", ".join(f"'{gid}'" for gid in candidate_geo_ids)

    query = f"""
    WITH city_baseline AS (
      SELECT
        ROUND(AVG(CASE WHEN median_income > 0 THEN median_income END), 0) AS city_avg_income,
        ROUND(AVG(poverty_rate) * 100, 1) AS city_avg_poverty_pct,
        ROUND(AVG(no_vehicle_rate) * 100, 1) AS city_avg_no_vehicle_pct,
        ROUND(AVG(median_age), 1) AS city_avg_age,
        COUNT(*) AS total_tracts_city
      FROM `{PROJECT_ID}.{DATASET_ID}.tract_demographics`
      WHERE total_pop > 0
    ),
    recommended_sample AS (
      SELECT
        ROUND(AVG(CASE WHEN median_income > 0 THEN median_income END), 0) AS rec_avg_income,
        ROUND(AVG(poverty_rate) * 100, 1) AS rec_avg_poverty_pct,
        ROUND(AVG(no_vehicle_rate) * 100, 1) AS rec_avg_no_vehicle_pct,
        ROUND(AVG(median_age), 1) AS rec_avg_age,
        SUM(total_pop) AS total_population_served,
        COUNT(*) AS num_recommended_tracts
      FROM `{PROJECT_ID}.{DATASET_ID}.tract_demographics`
      WHERE geo_id IN ({formatted_ids})
    )
    SELECT * FROM city_baseline CROSS JOIN recommended_sample
    """

    try:
        results = bq_client.query(query).result()
        row = next(iter(results), None)
        if not row:
            return {"error": "Could not calculate equity audit metrics."}

        poverty_ratio = (
            round(row.rec_avg_poverty_pct / row.city_avg_poverty_pct, 2)
            if row.city_avg_poverty_pct else 1.0
        )
        no_car_ratio = (
            round(row.rec_avg_no_vehicle_pct / row.city_avg_no_vehicle_pct, 2)
            if row.city_avg_no_vehicle_pct else 1.0
        )

        equitable = poverty_ratio >= 1.0 and no_car_ratio >= 1.0

        return {
            "num_tracts_evaluated": row.num_recommended_tracts,
            "total_population_served": int(row.total_population_served) if row.total_population_served else 0,
            "comparison_table": {
                "metric": ["Poverty Rate", "No-Vehicle Rate", "Median Household Income", "Median Age"],
                "recommended_sites_avg": [
                    f"{row.rec_avg_poverty_pct}%",
                    f"{row.rec_avg_no_vehicle_pct}%",
                    f"${int(row.rec_avg_income):,}" if row.rec_avg_income else "N/A",
                    f"{row.rec_avg_age} yrs"
                ],
                "citywide_average": [
                    f"{row.city_avg_poverty_pct}%",
                    f"{row.city_avg_no_vehicle_pct}%",
                    f"${int(row.city_avg_income):,}" if row.city_avg_income else "N/A",
                    f"{row.city_avg_age} yrs"
                ]
            },
            "equity_ratio": {
                "poverty_exposure_multiplier": poverty_ratio,
                "transit_dependent_multiplier": no_car_ratio
            },
            "audit_verdict": (
                "PASS: Recommendations equitably prioritize high-vulnerability populations."
                if equitable
                else "NOTE: Recommended tracts have lower vulnerability than city average; consider re-weighting transit-dependent areas."
            )
        }
    except Exception as e:
        return {"error": f"Failed to execute equity audit: {str(e)}"}
