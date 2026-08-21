#!/usr/bin/env python3
"""
Look up the CFFDRS FBP fuel type at a point via the CWFIS geoserver WMS
GetFeatureInfo on layer public:cffdrs_fbp_fuel_types (found by probing
https://cwfis.cfs.nrcan.gc.ca/geoserver/wms GetCapabilities — this layer
wasn't in the original input folder's sources.md, which listed fuel-type
data as a follow-up gap; it exists and is queryable per-point).

This closes the "no fuel-type data" gap enough to *label* a location's
fuel type, but does not implement the full Fire Behaviour Prediction
(FBP) System (spread rate, intensity) — that needs slope, crown closure,
and more per-fuel-type parameters beyond this POC's scope.
"""
import json
import urllib.request

WMS_URL = "https://cwfis.cfs.nrcan.gc.ca/geoserver/wms"
LAYER = "public:cffdrs_fbp_fuel_types"


def fetch_fuel_type(lat, lon, box_deg=0.01):
    url = (
        f"{WMS_URL}?service=WMS&version=1.1.1&request=GetFeatureInfo"
        f"&LAYERS={LAYER}&QUERY_LAYERS={LAYER}"
        f"&BBOX={lon - box_deg},{lat - box_deg},{lon + box_deg},{lat + box_deg}"
        "&SRS=EPSG:4326&WIDTH=101&HEIGHT=101&X=50&Y=50"
        "&INFO_FORMAT=application/json&FEATURE_COUNT=1"
    )
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.loads(r.read())

    features = data.get("features", [])
    if not features:
        return {"status": "not_available", "fuel_type_code": None, "fuel_type_label": None}

    props = features[0]["properties"]
    label_key = next((k for k in props if k.lower().startswith("label")), None)
    code_key = next((k for k in props if "fuel_type" in k.lower() and not k.lower().startswith("label")), None)
    return {
        "status": "found",
        "fuel_type_code": props.get(code_key) if code_key else None,
        "fuel_type_label": props.get(label_key) if label_key else None,
        "source": "CWFIS geoserver WMS, layer " + LAYER,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    args = parser.parse_args()
    print(json.dumps(fetch_fuel_type(args.lat, args.lon), indent=2))
