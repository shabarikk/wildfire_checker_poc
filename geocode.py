#!/usr/bin/env python3
"""
Resolve a free-text place name (city, town, lake, etc.) to a lat/lon using
the Open-Meteo Geocoding API (free, no key: https://open-meteo.com/en/docs/geocoding-api).

Deliberately does NOT fall back across country borders on a weak match:
if nothing in Canada matches the query, that is reported as an explicit
"not found" rather than silently returning e.g. a same-named place in
Australia (this happened during testing: "Fort St John" with no country
filter matched a mountain in Queensland before a period was added to the
query — "Fort St. John").
"""
import json
import sys
import urllib.parse
import urllib.request

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


class LocationNotFound(Exception):
    pass


def geocode(query, country_code="CA", count=10):
    url = f"{GEOCODE_URL}?name={urllib.parse.quote(query)}&count={count}&language=en&format=json"
    if country_code:
        url += f"&countryCode={country_code}"
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read())

    results = data.get("results", [])
    if not results:
        raise LocationNotFound(
            f"No location matching '{query}' found in "
            f"{'country ' + country_code if country_code else 'any country'}. "
            "Nothing was guessed — try a different spelling (e.g. abbreviations "
            "like 'St' vs 'St.' matter to the geocoder)."
        )

    best = results[0]
    return {
        "query": query,
        "matched_name": best.get("name"),
        "latitude": best.get("latitude"),
        "longitude": best.get("longitude"),
        "elevation_m": best.get("elevation"),
        "feature_code": best.get("feature_code"),
        "admin1": best.get("admin1"),
        "country_code": best.get("country_code"),
        "candidates_considered": len(results),
        "other_candidates": [
            {"name": c.get("name"), "admin1": c.get("admin1"), "country_code": c.get("country_code")}
            for c in results[1:5]
        ],
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="place name to geocode, e.g. 'Kelowna' or 'Adams Lake'")
    parser.add_argument("--country-code", default="CA")
    args = parser.parse_args()
    try:
        result = geocode(args.query, country_code=args.country_code)
        print(json.dumps(result, indent=2))
    except LocationNotFound as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
