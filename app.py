#!/usr/bin/env python3
import mimetypes
import os

from flask import Flask, jsonify, render_template, request

from build_report import build_report
from geocode import LocationNotFound
from llm_client import build_travel_advisory_headline, LLMError

mimetypes.add_type("font/woff2", ".woff2")

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/report")
def api_report():
    query = request.args.get("query", "").strip()
    if not query:
        return jsonify({"error": "Missing 'query' parameter."}), 400

    radius_km = request.args.get("radius_km", default=50, type=float)

    try:
        report = build_report(query, radius_km=radius_km)
    except LocationNotFound as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"Report generation failed: {e}"}), 502

    if "error" in report:
        return jsonify(report), 404

    try:
        report["travel_advisory_headline"] = build_travel_advisory_headline(report)
    except LLMError:
        # The deterministic report is still useful on its own -- an LLM
        # hiccup shouldn't take down the whole request, just the banner.
        report["travel_advisory_headline"] = None

    return jsonify(report)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
