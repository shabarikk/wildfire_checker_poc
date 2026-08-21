#!/usr/bin/env python3
"""
Fetch current-season BC Wildfire Service fire points (WFS GetFeature,
GeoJSON) and return those within a radius of a query point, nearest
first.

Note: fetch_bc_fire_points.py (the script that shipped in this input
folder) pulls the equivalent KML, but that KML is a NetworkLink stub
pointing at a WMS image layer — it has no per-fire coordinates. This
module goes through the WFS endpoint instead, which returns real
per-feature LATITUDE/LONGITUDE properties.
"""
import json
import math
import urllib.request

WFS_URL = "https://openmaps.gov.bc.ca/geo/pub/wfs"
LAYER = "pub:WHSE_LAND_AND_NATURAL_RESOURCE.PROT_CURRENT_FIRE_PNTS_SP"


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def fetch_all_fire_points(max_count=2000):
    url = (
        f"{WFS_URL}?service=WFS&version=2.0.0&request=GetFeature"
        f"&typeName={LAYER}&outputFormat=json&count={max_count}"
    )
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.loads(r.read())
    return data


def nearby_fires(lat, lon, radius_km=50):
    data = fetch_all_fire_points()
    total = data.get("totalFeatures")
    returned = data.get("numberReturned", len(data.get("features", [])))
    truncated = isinstance(total, int) and returned < total

    results = []
    for feat in data.get("features", []):
        p = feat["properties"]
        flat, flon = p.get("LATITUDE"), p.get("LONGITUDE")
        if flat is None or flon is None:
            continue
        dist = _haversine_km(lat, lon, flat, flon)
        if dist <= radius_km:
            results.append({
                "fire_number": p.get("FIRE_NUMBER"),
                "status": p.get("FIRE_STATUS"),
                "cause": p.get("FIRE_CAUSE"),
                "ignition_date": p.get("IGNITION_DATE"),
                "fire_out_date": p.get("FIRE_OUT_DATE"),
                "latitude": flat,
                "longitude": flon,
                "current_size_ha": p.get("CURRENT_SIZE"),
                "distance_km": round(dist, 1),
                "fire_url": p.get("FIRE_URL"),
                "geographic_description": p.get("GEOGRAPHIC_DESCRIPTION"),
            })

    results.sort(key=lambda f: f["distance_km"])
    return {
        "fires": results,
        "search_radius_km": radius_km,
        "total_features_in_source": total,
        "features_scanned": returned,
        "scan_truncated": truncated,  # True would mean not all BC fires were checked — must be surfaced, not hidden
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--radius-km", type=float, default=50)
    args = parser.parse_args()
    print(json.dumps(nearby_fires(args.lat, args.lon, args.radius_km), indent=2))
