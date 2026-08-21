#!/usr/bin/env python3
"""
End-to-end wildfire-likelihood report for a place name (city, town, lake).

Query by name -> geocode -> weather history -> FWI calculation ->
fuel type at point -> nearby current fires. Output matches
proposed_schema.json. Nothing here is invented: any missing input
shows up as an explicit status/limitation field rather than a guessed
number.
"""
import argparse
import json
import sys
from datetime import date

from geocode import geocode, LocationNotFound
from weather_history import fetch_weather_series
from fuel_type import fetch_fuel_type
from fires import nearby_fires
from fwi import run_daily_series, fwi_class, forecast_window


def build_report(query, radius_km=50, country_code="CA"):
    limitations = [
        "No Fire Behaviour Prediction (spread rate, intensity) is calculated — "
        "only the Fire Weather Index (fire-weather danger), per fwi.py's "
        "fwi_class(). FBP needs slope and crown-closure data beyond this POC.",
        "Daily weather aggregates (temp max, RH min, wind max) are used as a "
        "proxy for the FWI system's official noon-LST readings — see the "
        "docstring in weather_history.py. This can read drier/higher than a "
        "true noon-only observation on some days.",
        "nearby_fires reflects BC Wildfire Service reported/mapped locations "
        "only, not lightning-strike forecasting or ignition-risk modeling.",
    ]

    try:
        loc = geocode(query, country_code=country_code)
    except LocationNotFound as e:
        return {"error": str(e), "query": query}

    # geocode()'s countryCode="CA" filter admits all of Canada, not just BC --
    # that's deliberate, so geocode.py stays reusable for a future province
    # (see the wildfire-likelihood skill's extension notes). But fires.py only
    # queries BC Wildfire Service, so a non-BC match here would silently
    # render "0 nearby fires" as if that meant something, when it actually
    # just means the wrong province's fire feed was checked. Reject it here,
    # at the point where the BC-specific pieces get tied together, rather
    # than in geocode.py itself.
    if loc["admin1"] != "British Columbia":
        return {
            "error": (
                f"'{query}' resolved to {loc['matched_name']}, {loc['admin1']} — "
                "this app only covers British Columbia. BC Wildfire Service has "
                "no fire data for other provinces, so a report there would be "
                "misleading rather than just incomplete."
            ),
            "query": query,
        }

    weather = fetch_weather_series(loc["latitude"], loc["longitude"], forecast_days=7)
    if weather["coverage"]["is_cold_start"]:
        limitations.append(
            f"Only {weather['coverage']['days_available']} days of clean weather "
            f"history were available (need ~{weather['coverage']['days_required_for_stable_dc']} "
            "for a stable Drought Code) — dc/bui/fwi below are cold-start estimates, "
            "not true seasonal values."
        )

    fwi_series = run_daily_series(weather["daily"], lat=loc["latitude"])
    # Pick today's entry specifically for the headline rating below — not
    # fwi_series[-1], which is now the far end of the 7-day forecast window
    # and would silently mislabel "today" as whatever the last forecast day is.
    today_str = date.today().isoformat()
    latest = next((d for d in fwi_series if d["date"] == today_str), None) or (fwi_series[-1] if fwi_series else None)

    forecast_7day = forecast_window(fwi_series, today=date.today(), days=7)
    if any(day["status"] != "calculated" for day in forecast_7day):
        limitations.append(
            "forecast_7day includes one or more days without a calculated FWI value "
            "(forecast weather unavailable for that date, or a gap in the merged "
            "weather series) — see each day's status field rather than treating a "
            "missing day as low danger."
        )

    fuel = fetch_fuel_type(loc["latitude"], loc["longitude"])
    if fuel["status"] != "found":
        limitations.append("Fuel type could not be resolved for this exact point (outside mapped coverage).")

    fires = nearby_fires(loc["latitude"], loc["longitude"], radius_km=radius_km)
    if fires["scan_truncated"]:
        limitations.append(
            f"Only {fires['features_scanned']} of {fires['total_features_in_source']} "
            "province-wide fire records were scanned for proximity — nearby_fires may be incomplete."
        )

    danger_class = fwi_class(latest["fwi"]["value"]) if latest and latest["fwi"]["value"] is not None else "not_calculated"

    return {
        "report_meta": {
            "query": query,
            "source_versions": {
                "weather_source": "open-meteo",
                "fire_points_source": "bc-wildfire-service-wfs",
            },
        },
        "location": {
            "latitude": loc["latitude"],
            "longitude": loc["longitude"],
            "name": loc["matched_name"],
            "elevation_m": loc["elevation_m"],
            "admin1": loc["admin1"],
        },
        "weather_input": {
            "daily": weather["daily"],
            "coverage": weather["coverage"],
        },
        "fwi_indices": latest if latest else {"status": "not_calculated"},
        "fwi_history_last_7_days": fwi_series[-7:],
        "forecast_7day": forecast_7day,
        "danger_rating": {
            "class": danger_class,
            "basis": "fire_weather_index",
            "class_source": "CWFIS WMS style 'cffdrs_fwi' (layer public:fwi_current): "
                             "breaks at 5/10/20/30, labels Low/Moderate/High/Very High/Extreme",
            "disclaimer": (
                "This rating reflects fire weather danger (FWI), not predicted fire "
                "behavior or spread rate. Fire Behaviour Prediction (FBP) requires "
                "fuel-type and terrain data beyond this POC's scope."
            ),
        },
        "fuel_type": fuel,
        "nearby_fires": fires["fires"],
        "nearby_fires_meta": {
            "search_radius_km": fires["search_radius_km"],
            "total_features_in_source": fires["total_features_in_source"],
            "features_scanned": fires["features_scanned"],
        },
        "limitations": limitations,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="place name, e.g. 'Kelowna' or 'Adams Lake'")
    parser.add_argument("--radius-km", type=float, default=50)
    args = parser.parse_args()
    report = build_report(args.query, radius_km=args.radius_km)
    if "error" in report:
        print(f"ERROR: {report['error']}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(report, indent=2))
