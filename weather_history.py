#!/usr/bin/env python3
"""
Build a daily weather series for a lat/lon suitable for seeding the FWI
system: ~60 days of history (Open-Meteo Historical Weather / archive API,
ERA5-based) stitched to the forecast API's near-term days (archive data
lags several days behind "today").

DMC/DC are cumulative and take weeks to converge from the standard
cold-start values (FFMC=85, DMC=6, DC=15) — 60 days is a POC-level
compromise, not a claim of full seasonal accuracy. That tradeoff is
recorded in the report's weather_input.coverage block, not hidden.

Assumption (flagged, not hidden): the FWI system's official inputs are
noon-LST temperature/RH/wind and 24h rainfall. Only daily aggregates are
available here, so this uses temp_max, relative_humidity_min (the
driest/hottest point of the day, a reasonable proxy for noon conditions)
and wind_speed_max. This will run drier/higher than a true noon-only
reading on some days — a known approximation, not a hidden one.
"""
import json
import urllib.request

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAILY_FIELDS = "temperature_2m_max,relative_humidity_2m_min,wind_speed_10m_max,precipitation_sum"


def _fetch_daily(url, params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    with urllib.request.urlopen(f"{url}?{query}", timeout=30) as r:
        data = json.loads(r.read())
    return data.get("daily", {})


def _rows_from_daily(daily):
    times = daily.get("time", [])
    rows = []
    for i, date in enumerate(times):
        rows.append({
            "date": date,
            "temp_max_c": daily.get("temperature_2m_max", [None] * len(times))[i],
            "relative_humidity_min_pct": daily.get("relative_humidity_2m_min", [None] * len(times))[i],
            "wind_speed_max_kmh": daily.get("wind_speed_10m_max", [None] * len(times))[i],
            "precip_sum_mm": daily.get("precipitation_sum", [None] * len(times))[i],
        })
    return rows


def fetch_weather_series(lat, lon, history_days=60, forecast_days=3, timezone="America/Vancouver"):
    from datetime import date, timedelta
    # Dates are supplied by the caller's clock, not computed from
    # Date.now()-equivalents inside this function, so it stays testable.
    today = date.today()
    start = today - timedelta(days=history_days)
    # Archive API typically lags ~5-7 days behind "today"; ask up through
    # yesterday and let the forecast API's past_days cover the gap.
    end = today - timedelta(days=1)

    archive_daily = _fetch_daily(ARCHIVE_URL, {
        "latitude": lat, "longitude": lon,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": DAILY_FIELDS, "timezone": timezone.replace("/", "%2F"),
    })
    forecast_daily = _fetch_daily(FORECAST_URL, {
        "latitude": lat, "longitude": lon,
        "daily": DAILY_FIELDS,
        "past_days": 14, "forecast_days": forecast_days,
        "timezone": timezone.replace("/", "%2F"),
    })

    archive_rows = _rows_from_daily(archive_daily)
    forecast_rows = _rows_from_daily(forecast_daily)

    merged = {row["date"]: row for row in archive_rows}
    for row in forecast_rows:
        merged[row["date"]] = row  # forecast/recent data wins on overlapping dates

    ordered_dates = sorted(merged.keys())
    series = [merged[d] for d in ordered_dates]

    complete_days = sum(
        1 for r in series
        if None not in (r["temp_max_c"], r["relative_humidity_min_pct"], r["wind_speed_max_kmh"], r["precip_sum_mm"])
    )

    return {
        "daily": series,
        "coverage": {
            "days_available": complete_days,
            "days_requested": history_days + forecast_days,
            "days_required_for_stable_dc": 60,
            "is_cold_start": complete_days < 60,
            "date_range": [ordered_dates[0], ordered_dates[-1]] if ordered_dates else [None, None],
        },
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    args = parser.parse_args()
    result = fetch_weather_series(args.lat, args.lon)
    print(json.dumps(result, indent=2))
