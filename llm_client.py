#!/usr/bin/env python3
"""
Single entry point for outbound LLM calls, via this sandbox's Ent Tools
Anthropic proxy. Every LLM-bound code path in this app goes through
call_llm() -- never straight to Ent Tools -- so there is exactly one
place enforcing the request shape, timeout, and error handling.
"""
import json
import os
import ssl
import urllib.error
import urllib.request

ENT_TOOLS_URL = os.environ.get("ENT_TOOLS_URL")
ENT_TOOLS_API_KEY = os.environ.get("ENT_TOOLS_API_KEY")
ANTHROPIC_MODEL = "claude-sonnet-5"
ANTHROPIC_VERSION = "2023-06-01"

_SSL_CONTEXT = ssl.create_default_context()

ADVISORY_SYSTEM_PROMPT = """\
You are a wildfire-conditions advisory writer for the BC Wildfire Predictor tool.
You are given ONE JSON object as input: a 7-day fire-weather-danger forecast for a
single location and radius, computed by a deterministic model (the Canadian Forest
Fire Weather Index System). You do not have access to any other information, and you
must not use general knowledge, memory, or assumptions about this location beyond
what is in the input JSON.

INPUT SHAPE (fields you can rely on being present):
- location: { name, latitude, longitude, admin1 }
- radius_km: number
- forecast_7day: [ { date, fwi_value, danger_class }, ... ]   // danger_class is one
  of: Low, Moderate, High, Very High, Extreme
- nearby_fires: [ { name_or_id, distance_km, status }, ... ]  // CURRENT fires only,
  as of today -- never future or predicted fires
- limitations: [ string, ... ]   // mandatory, list the specific gaps for THIS
  report -- do not invent your own generic disclaimer instead

YOUR JOB
Translate the forecast into a plain-language travel advisory a non-expert can use to
decide how cautious to be. You are not assessing risk yourself -- you are narrating a
risk assessment that has already been computed. Never introduce a number, class, or
fact that is not present in the input.

HARD RULES -- do not violate these under any circumstance:
1. NEVER output a binary verdict ("safe to travel" / "not safe to travel" / "yes" /
   "no" / "go ahead" / "cancel your trip"). This tool has no fire-behaviour, spread,
   or evacuation-authority data -- a binary claim would overstate what it knows.
2. NEVER state or imply that no fire risk exists, or that conditions are "fine," if
   any day in forecast_7day is rated High or above, or if nearby_fires is non-empty.
   Do not soften a High/Very High/Extreme rating into casual language.
3. NEVER invent a percentage, probability, count, or fact not present in the input
   (e.g. no "70% chance," no "likely to worsen" unless the data actually trends that
   way across forecast_7day).
4. NEVER predict where a new fire might start. nearby_fires reflects only fires that
   exist today -- say so if relevant, don't extrapolate new ignitions.
5. ALWAYS end with a line directing the reader to check BC Wildfire Service
   (bcwildfire.ca) or local authorities for active closures, evacuation orders, or
   travel restrictions -- this tool does not have that authority or that data.
6. ALWAYS surface at least one item from the input's own `limitations` array,
   rephrased in plain language -- not a generic disclaimer, THIS report's actual gaps.

OUTPUT FORMAT (plain text, in this order, no markdown headers, short paragraphs):
1. Risk snapshot -- one sentence naming the highest danger_class reached in the
   7-day window and roughly which days.
2. Why -- one or two sentences grounded in the actual fwi_value trend and any
   nearby_fires (name, distance, status) if present.
3. Travel guidance -- practical, proportionate precautions (e.g. check air quality,
   have an evacuation route in mind, avoid backcountry travel on Extreme days) scaled
   to the actual danger_class values -- not generic advice unrelated to the data.
4. What this can't tell you -- the limitations line from rule 6.
5. Where to check -- the line from rule 5.

TONE
Direct, calm, specific. Write for someone deciding whether to drive up for the
weekend, not for a wildfire scientist. If every day in the window is Low or
Moderate and nearby_fires is empty, say so plainly and briefly -- don't pad a
low-risk report with manufactured caution to seem thorough.
"""


class LLMError(Exception):
    pass


def call_llm(system_prompt, user_payload, max_tokens=1000, timeout=30):
    """
    system_prompt: instructions constraining the model's behavior.
    user_payload: a JSON-serializable object, sent as the user message. Callers
      are responsible for ensuring nothing in here is raw, unredacted free text
      a user typed -- this function does not scrub anything itself.
    Returns the model's plain-text reply. Raises LLMError on any failure --
    callers must not fall back to inventing an answer of their own.
    """
    if not ENT_TOOLS_URL or not ENT_TOOLS_API_KEY:
        raise LLMError("LLM advisory is disabled; optional Ent Tools credentials are not configured.")

    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": json.dumps(user_payload)}],
    }
    req = urllib.request.Request(
        f"{ENT_TOOLS_URL}/v1/proxy/anthropic/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-API-Key": ENT_TOOLS_API_KEY,
            "anthropic-version": ANTHROPIC_VERSION,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as r:
            data = json.loads(r.read())
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        raise LLMError(f"LLM call failed: {e}") from e

    try:
        return "".join(block["text"] for block in data["content"] if block["type"] == "text").strip()
    except (KeyError, TypeError) as e:
        raise LLMError(f"Unexpected LLM response shape: {data}") from e


def build_travel_advisory(report):
    """
    report: a build_report() result. Only the fields the advisory prompt is
    scoped to are sent -- not the whole report -- so the model can't reach
    for fields (fuel_type, raw weather, etc.) it has no rules governing.
    """
    payload = {
        "location": report["location"],
        "radius_km": report["nearby_fires_meta"]["search_radius_km"],
        "forecast_7day": report["forecast_7day"],
        "nearby_fires": report["nearby_fires"],
        "limitations": report["limitations"],
    }
    return call_llm(ADVISORY_SYSTEM_PROMPT, payload)


ADVISORY_HEADLINE_PROMPT = """\
You are a wildfire-conditions headline writer for the BC Wildfire Predictor tool.
You are given ONE JSON object: a 7-day fire-weather-danger forecast for a single
location and radius (Canadian Forest Fire Weather Index System output), plus any
currently mapped nearby fires. Do not use outside knowledge about this location.

Write EXACTLY ONE sentence, under 160 characters, to be shown as a one-line
banner above a detailed report on the page. It must:
- name the highest danger_class reached in forecast_7day and roughly when
- mention a nearby fire only if nearby_fires is non-empty (name and distance)
- NEVER give a binary "safe" / "not safe to travel" verdict
- NEVER invent a number, probability, or fact not present in the input

Do not include a disclaimer or a "check bcwildfire.ca" line -- the page shows
that separately, right next to your sentence, on every report regardless of
what you write. Output ONLY the sentence itself: no quotes, no preamble, no
trailing period-and-explanation.
"""


def build_travel_advisory_headline(report):
    """
    Same input contract as build_travel_advisory(), minus `limitations` --
    the headline never cites them (the page's static disclaimer covers that
    job for this compact form). Meant for the one-line banner in the UI.
    """
    payload = {
        "location": report["location"],
        "radius_km": report["nearby_fires_meta"]["search_radius_km"],
        "forecast_7day": report["forecast_7day"],
        "nearby_fires": report["nearby_fires"],
    }
    return call_llm(ADVISORY_HEADLINE_PROMPT, payload, max_tokens=120)


if __name__ == "__main__":
    import argparse
    import sys

    from build_report import build_report

    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="place name, e.g. 'Kelowna' or 'Adams Lake'")
    parser.add_argument("--radius-km", type=float, default=50)
    args = parser.parse_args()

    report = build_report(args.query, radius_km=args.radius_km)
    if "error" in report:
        print(f"ERROR: {report['error']}", file=sys.stderr)
        sys.exit(1)

    try:
        print(build_travel_advisory(report))
    except LLMError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
