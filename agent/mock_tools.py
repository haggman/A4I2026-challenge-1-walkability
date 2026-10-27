"""Mock tools for offline development, local unit tests, and front-end scaffolding.

Enables immediate testing of the ADK agent and UI before BigQuery credentials
or Cloud Run connections are initialized.
"""

from typing import Any, Dict, List

def mock_predict_heat_offset(latitude: float, longitude: float) -> Dict[str, Any]:
    """Mock implementation of microclimate heat offset prediction."""
    # Deterministic mock offset based on coordinate decimals
    pseudo_offset = round(((latitude * 100) % 7) - 3.2, 2)
    risk_level = "Severe Urban Heat Island" if pseudo_offset > 1.5 else "Moderate Exposure"
    return {
        "latitude": latitude,
        "longitude": longitude,
        "predicted_temp_offset_f": pseudo_offset,
        "interpretation": f"This location runs {abs(pseudo_offset)}°F {'warmer' if pseudo_offset >= 0 else 'cooler'} than city baseline.",
        "heat_risk_level": risk_level,
        "feature_attributions": [
            {"feature": "impervious_surface_density", "attribution": 1.45},
            {"feature": "canopy_deficit", "attribution": 0.88},
            {"feature": "northing_km", "attribution": 0.32}
        ]
    }

def mock_rank_candidate_sites(limit: int = 3) -> List[Dict[str, Any]]:
    """Mock implementation of candidate site ranking."""
    return [
        {
            "rank": 1,
            "census_tract": "48113020300",
            "coordinates": {"latitude": 32.7743, "longitude": -96.7668},
            "predicted_temp_offset_f": 1.25,
            "composite_vulnerability_score": 34.11,
            "population": 4120,
            "median_age": 34.2,
            "median_income": 28450.0,
            "poverty_rate_pct": 30.1,
            "no_vehicle_rate_pct": 38.5,
            "key_heat_drivers": ["impervious_surface_density (+1.45°F)", "canopy_deficit (+0.88°F)"]
        },
        {
            "rank": 2,
            "census_tract": "48113008704",
            "coordinates": {"latitude": 32.6952, "longitude": -96.7815},
            "predicted_temp_offset_f": 0.95,
            "composite_vulnerability_score": 32.86,
            "population": 3892,
            "median_age": 36.4,
            "median_income": 24100.0,
            "poverty_rate_pct": 52.2,
            "no_vehicle_rate_pct": 33.5,
            "key_heat_drivers": ["commercial_pavement (+1.10°F)", "building_density (+0.65°F)"]
        },
        {
            "rank": 3,
            "census_tract": "48113020500",
            "coordinates": {"latitude": 32.7834, "longitude": -96.8623},
            "predicted_temp_offset_f": 0.72,
            "composite_vulnerability_score": 31.26,
            "population": 5166,
            "median_age": 38.1,
            "median_income": 31200.0,
            "poverty_rate_pct": 29.1,
            "no_vehicle_rate_pct": 45.2,
            "key_heat_drivers": ["transit_stop_density (+0.54°F)", "residential_density (+0.42°F)"]
        }
    ][:limit]

def mock_analyze_heat_frequency(temp_threshold_f: float = 100.0) -> Dict[str, Any]:
    """Mock implementation of historical heat frequency analysis."""
    return {
        "threshold_f": temp_threshold_f,
        "average_annual_days_above_threshold": 256.6,
        "worst_year_on_record": {
            "year": 2023,
            "days_above_threshold": 612,
            "record_high_f": 111.9
        },
        "yearly_breakdown": [
            {"year": 2020, "days_above_threshold": 194, "record_high_f": 105.8, "summer_avg_high_f": 96.1},
            {"year": 2021, "days_above_threshold": 118, "record_high_f": 102.2, "summer_avg_high_f": 93.8},
            {"year": 2022, "days_above_threshold": 412, "record_high_f": 109.4, "summer_avg_high_f": 98.4},
            {"year": 2023, "days_above_threshold": 612, "record_high_f": 111.9, "summer_avg_high_f": 100.2},
            {"year": 2024, "days_above_threshold": 320, "record_high_f": 106.5, "summer_avg_high_f": 97.0}
        ],
        "resilience_implication": (
            f"The city averages 256.6 station-days above {temp_threshold_f}°F each summer. "
            f"Microclimate hotspots with positive offsets cross this threshold even more frequently."
        )
    }

def mock_audit_equity(candidate_geo_ids: List[str]) -> Dict[str, Any]:
    """Mock implementation of equity auditing."""
    return {
        "num_tracts_evaluated": len(candidate_geo_ids),
        "total_population_served": 13178,
        "comparison_table": {
            "metric": ["Poverty Rate", "No-Vehicle Rate", "Median Household Income", "Median Age"],
            "recommended_sites_avg": ["37.1%", "39.1%", "$29,800", "36.2 yrs"],
            "citywide_average": ["12.2%", "5.3%", "$62,400", "35.1 yrs"]
        },
        "equity_ratio": {
            "poverty_exposure_multiplier": 3.04,
            "transit_dependent_multiplier": 7.38
        },
        "audit_verdict": "PASS: Recommendations equitably prioritize high-vulnerability populations."
    }
