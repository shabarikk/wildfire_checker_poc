#!/usr/bin/env python3
"""
Canadian Forest Fire Weather Index (FWI) System.

Ported directly from the official cffdrs R package source
(https://github.com/cffdrs/cffdrs_r, files fine_fuel_moisture_code.r,
duff_moisture_code.r, drought_code.r, initial_spread_index.r,
buildup_index.r, fire_weather_index.r — fetched into cffdrs_r_reference/
in this folder). Formula bodies and constants are unchanged from that
source; only the language and the daily-series wrapper are new.

Reference: Van Wagner, C.E.; Pickett, T.L. 1985. Equations and FORTRAN
program for the Canadian Forest Fire Weather Index System. Canadian
Forestry Service, Forestry Technical Report 33.
"""
import math
from datetime import date, timedelta

FFMC_COEFFICIENT = 250.0 * 59.5 / 101.0

# Effective day-length factors for DMC, by month (Jan..Dec), latitude >= 30N.
# Van Wagner (1987). Only the >=30N table is implemented — this POC's
# scope is BC, which is entirely north of 30N.
DMC_DAYLENGTH_30N = [6.5, 7.5, 9, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8, 7, 6]

# Day-length factor for DC, by month (Jan..Dec), latitude >= 20N.
DC_DAYLENGTH_20N = [-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5, 2.4, 0.4, -1.6, -1.6]

# Official CWFIS FWI class breakpoints, taken directly from the published
# WMS style for layer public:fwi_current (style name "cffdrs_fwi"):
# ColorMapEntry quantities 5.001 / 10.001 / 20.001 / 30.001 / Infinity.
# Class names (Low/Moderate/.../Extreme) are the conventional labels for
# those five bands; CWFIS's own legend does not print the words, only the
# numeric ranges and colors.
FWI_CLASS_BREAKS = [
    (5.001, "low"),
    (10.001, "moderate"),
    (20.001, "high"),
    (30.001, "very_high"),
    (math.inf, "extreme"),
]

# Same approach as FWI_CLASS_BREAKS above, but for each of the five
# component codes — taken from CWFIS's own published WMS legends for
# public:ffmc_current / dmc_current / dc_current / isi_current /
# bui_current (style GetStyles ColorMapEntry quantities). BUI's source
# legend actually has 6 bands (two shades of green); merged the two green
# bands into a single "moderate" tier here to match the 5-name taxonomy
# used everywhere else on the page.
FFMC_CLASS_BREAKS = [
    (74.01, "low"), (84.01, "moderate"), (88.01, "high"), (91.01, "very_high"), (math.inf, "extreme"),
]
DMC_CLASS_BREAKS = [
    (21.01, "low"), (27.01, "moderate"), (40.01, "high"), (60.01, "very_high"), (math.inf, "extreme"),
]
DC_CLASS_BREAKS = [
    (80, "low"), (190, "moderate"), (300, "high"), (425, "very_high"), (math.inf, "extreme"),
]
ISI_CLASS_BREAKS = [
    (2.01, "low"), (5.01, "moderate"), (10.01, "high"), (15.01, "very_high"), (math.inf, "extreme"),
]
BUI_CLASS_BREAKS = [
    (20.01, "low"), (40.01, "moderate"), (60.01, "high"), (90.01, "very_high"), (math.inf, "extreme"),
]


def _classify(value, breaks):
    for upper, label in breaks:
        if value <= upper:
            return label
    return breaks[-1][1]


def fwi_class(fwi_value):
    return _classify(fwi_value, FWI_CLASS_BREAKS)


def fine_fuel_moisture_code(ffmc_yda, temp, rh, ws, prec):
    # Eq. 1
    wmo = FFMC_COEFFICIENT * (101 - ffmc_yda) / (59.5 + ffmc_yda)
    # Eq. 2 - rain reduction for canopy interception
    ra = prec - 0.5 if prec > 0.5 else prec
    # Eqs. 3a & 3b
    if prec > 0.5:
        if wmo > 150:
            wmo = (
                wmo + 0.0015 * (wmo - 150) ** 2 * math.sqrt(ra)
                + 42.5 * ra * math.exp(-100 / (251 - wmo)) * (1 - math.exp(-6.93 / ra))
            )
        else:
            wmo = wmo + 42.5 * ra * math.exp(-100 / (251 - wmo)) * (1 - math.exp(-6.93 / ra))
    wmo = min(wmo, 250)
    # Eq. 4 - equilibrium moisture content from drying
    ed = (
        0.942 * (rh ** 0.679) + (11 * math.exp((rh - 100) / 10))
        + 0.18 * (21.1 - temp) * (1 - 1 / math.exp(rh * 0.115))
    )
    # Eq. 5 - equilibrium moisture content from wetting
    ew = (
        0.618 * (rh ** 0.753) + (10 * math.exp((rh - 100) / 10))
        + 0.18 * (21.1 - temp) * (1 - 1 / math.exp(rh * 0.115))
    )
    if wmo < ed and wmo < ew:
        # Eq. 6a/6b - wetting rate
        z = 0.424 * (1 - (((100 - rh) / 100) ** 1.7)) + 0.0694 * math.sqrt(ws) * (
            1 - ((100 - rh) / 100) ** 8
        )
        x = z * 0.581 * math.exp(0.0365 * temp)
        # Eq. 9
        wm = ew - (ew - wmo) / (10 ** x)
    elif wmo > ed:
        # Eq. 7a/7b - drying rate
        z = 0.424 * (1 - (rh / 100) ** 1.7) + 0.0694 * math.sqrt(ws) * (1 - (rh / 100) ** 8)
        x = z * 0.581 * math.exp(0.0365 * temp)
        # Eq. 8
        wm = ed + (wmo - ed) / (10 ** x)
    else:
        wm = wmo
    # Eq. 10
    ffmc1 = (59.5 * (250 - wm)) / (FFMC_COEFFICIENT + wm)
    return max(0.0, min(101.0, ffmc1))


def duff_moisture_code(dmc_yda, temp, rh, prec, lat, mon):
    temp = max(temp, -1.1)
    ell = DMC_DAYLENGTH_30N[mon - 1]
    rk = 1.894 * (temp + 1.1) * (100 - rh) * ell * 1e-4

    if prec <= 1.5:
        pr = dmc_yda
    else:
        ra = prec
        rw = 0.92 * ra - 1.27  # Eq. 11
        wmi = 20 + 280 / math.exp(0.023 * dmc_yda)
        if dmc_yda <= 33:
            b = 100 / (0.5 + 0.3 * dmc_yda)
        elif dmc_yda <= 65:
            b = 14 - 1.3 * math.log(dmc_yda)
        else:
            b = 6.2 * math.log(dmc_yda) - 17.2
        wmr = wmi + 1000 * rw / (48.77 + b * rw)  # Eq. 14
        pr = 43.43 * (5.6348 - math.log(wmr - 20))
    pr = max(pr, 0.0)
    dmc1 = pr + rk
    return max(dmc1, 0.0)


def drought_code(dc_yda, temp, rh, prec, lat, mon):
    temp = max(temp, -2.8)
    fl = DC_DAYLENGTH_20N[mon - 1]
    pe = (0.36 * (temp + 2.8) + fl) / 2  # Eq. 22
    pe = max(pe, 0.0)

    if prec <= 2.8:
        dr = dc_yda
    else:
        rw = 0.83 * prec - 1.27  # Eq. 18
        smi = 800 * math.exp(-1 * dc_yda / 400)  # Eq. 19
        dr0 = dc_yda - 400 * math.log(1 + 3.937 * rw / smi)
        dr = max(dr0, 0.0)
    dc1 = dr + pe
    return max(dc1, 0.0)


def initial_spread_index(ffmc, ws):
    fm = FFMC_COEFFICIENT * (101 - ffmc) / (59.5 + ffmc)  # Eq. 10 (moisture)
    fw = math.exp(0.05039 * ws)  # Eq. 24
    ff = 91.9 * math.exp(-0.1386 * fm) * (1 + (fm ** 5.31) / 49300000)  # Eq. 25
    return 0.208 * fw * ff  # Eq. 26


def buildup_index(dmc, dc):
    if dmc == 0 and dc == 0:
        bui1 = 0.0
    else:
        bui1 = 0.8 * dc * dmc / (dmc + 0.4 * dc)  # Eq. 27a
    p = 0.0 if dmc == 0 else (dmc - bui1) / dmc
    cc = 0.92 + (0.0114 * dmc) ** 1.7
    bui0 = max(dmc - cc * p, 0.0)  # Eq. 27b
    return bui0 if bui1 < dmc else bui1


def fire_weather_index(isi, bui):
    if bui > 80:
        bb = 0.1 * isi * (1000 / (25 + 108.64 / math.exp(0.023 * bui)))  # Eq. 28b
    else:
        bb = 0.1 * isi * (0.626 * (bui ** 0.809) + 2)  # Eq. 28a
    if bb <= 1:
        return bb  # Eq. 30a
    return math.exp(2.72 * ((0.434 * math.log(bb)) ** 0.647))  # Eq. 30b


def run_daily_series(daily_weather, lat, start_codes=None):
    """
    daily_weather: list of dicts sorted oldest-first, each with
      date (str), temp_max_c, relative_humidity_min_pct, wind_speed_max_kmh,
      precip_sum_mm — or None for any field the source didn't provide.
    start_codes: optional {"ffmc": .., "dmc": .., "dc": ..} cold-start
      override. Defaults to the standard CFFDRS start-up values
      (FFMC=85, DMC=6, DC=15 — same defaults as cffdrs::fwi()).

    Returns a list of per-day dicts with the six index values, or with
    status "insufficient_data" for a day (and every day after it) where a
    required weather input was missing. Nothing is interpolated or guessed.
    """
    codes = dict(start_codes or {"ffmc": 85.0, "dmc": 6.0, "dc": 15.0})
    results = []
    broken = False

    for day in daily_weather:
        date = day["date"]
        month = int(date[5:7])
        temp = day.get("temp_max_c")
        rh = day.get("relative_humidity_min_pct")
        ws = day.get("wind_speed_max_kmh")
        prec = day.get("precip_sum_mm")

        if broken or None in (temp, rh, ws, prec):
            broken = True
            results.append({
                "date": date,
                "ffmc": {"value": None, "status": "insufficient_data", "class": None},
                "dmc": {"value": None, "status": "insufficient_data", "class": None},
                "dc": {"value": None, "status": "insufficient_data", "class": None},
                "isi": {"value": None, "status": "insufficient_data", "class": None},
                "bui": {"value": None, "status": "insufficient_data", "class": None},
                "fwi": {"value": None, "status": "insufficient_data", "class": None},
            })
            continue

        rh = min(max(rh, 0.0), 100.0)
        codes["ffmc"] = fine_fuel_moisture_code(codes["ffmc"], temp, rh, ws, prec)
        codes["dmc"] = duff_moisture_code(codes["dmc"], temp, rh, prec, lat, month)
        codes["dc"] = drought_code(codes["dc"], temp, rh, prec, lat, month)
        isi = initial_spread_index(codes["ffmc"], ws)
        bui = buildup_index(codes["dmc"], codes["dc"])
        fwi = fire_weather_index(isi, bui)

        results.append({
            "date": date,
            "ffmc": {"value": round(codes["ffmc"], 2), "status": "calculated", "class": _classify(codes["ffmc"], FFMC_CLASS_BREAKS)},
            "dmc": {"value": round(codes["dmc"], 2), "status": "calculated", "class": _classify(codes["dmc"], DMC_CLASS_BREAKS)},
            "dc": {"value": round(codes["dc"], 2), "status": "calculated", "class": _classify(codes["dc"], DC_CLASS_BREAKS)},
            "isi": {"value": round(isi, 2), "status": "calculated", "class": _classify(isi, ISI_CLASS_BREAKS)},
            "bui": {"value": round(bui, 2), "status": "calculated", "class": _classify(bui, BUI_CLASS_BREAKS)},
            "fwi": {"value": round(fwi, 2), "status": "calculated", "class": fwi_class(fwi)},
        })

    return results


def forecast_window(series, today, days=7):
    """
    Slice an already-computed run_daily_series() result to the forward-
    looking window [today, today + days - 1]. `series` must already reach
    that far via forecast-sourced weather (see
    weather_history.fetch_weather_series(forecast_days=...)) — this only
    reads and labels, it never invents a day's value. A requested day the
    series doesn't cover comes back with status "not_available" rather
    than being silently dropped, so a caller asking for 7 days who only
    had (say) 3 days of forecast weather available can see the gap
    instead of a report that quietly looks 7 days deep.
    """
    if isinstance(today, str):
        today = date.fromisoformat(today)
    by_date = {day["date"]: day for day in series}

    window = []
    for i in range(days):
        d = (today + timedelta(days=i)).isoformat()
        day = by_date.get(d)
        if day is None:
            window.append({"date": d, "fwi_value": None, "danger_class": None, "status": "not_available"})
        else:
            window.append({
                "date": d,
                "fwi_value": day["fwi"]["value"],
                "danger_class": day["fwi"]["class"],
                "status": day["fwi"]["status"],
            })
    return window
