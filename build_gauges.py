#!/usr/bin/env python3
"""Build the measured-gauges page (output/gauges.html, gauges.html on the website).

The page shows what the river actually did: the latest readings (up to 72 hours) of
Brisbane City Council's eight Brisbane River gauges, fetched live by the page itself
from the council's open data API, and BoM's Colleges Crossing gauge (540063), fetched
from the project's own copy on the gauge-data branch. No forecasting: predictions are
the other page.

What this script puts in the page: the gauge list with each gauge's position along the
river (chainage, km from Brisbane Bar), the river centreline for the map, and the MSQ
station names for the profile's axis. The readings are NOT built in; the page fetches
them when it opens, so it is always current without a rebuild.

  data/gauges.csv    the gauges and their chainage. Made once with --download, which
                     reads the council's gauge list and projects each gauge onto
                     data/centreline.csv; committed, so builds need no network.

Usage:
  python build_gauges.py                    # write output/gauges.html
  python build_gauges.py --download         # (re)make data/gauges.csv first
  python build_gauges.py --stamp --out site/gauges.html     # as the website is built

Sources and licences: docs/data-sources.md.
"""
import argparse
import csv
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from collect_gauges import BCC_GAUGES, USER_AGENT
from river_tides import BRISBANE, load_stations, station_labels, to_json

HERE = Path(__file__).parent
DATA = HERE / "data"
GAUGES_CSV = DATA / "gauges.csv"
METADATA_URL = ("https://data.brisbane.qld.gov.au/api/explore/v2.1/catalog/datasets/"
                "telemetry-sensors-rainfall-and-stream-heights-metadata/exports/json")

# Short names for the profile's axis and the map labels.
SHORT = {
    "E1594": "Breakfast Ck", "E1857": "Hawthorne", "E6749": "City Gauge",
    "E1855": "Port Office", "E1856": "St Lucia", "E1588": "Oxley Ck",
    "E1765": "Jindalee", "E1764": "Moggill",
}


def project_onto(cl, lon, lat):
    """Chainage (km) of the nearest point on the centreline, and the distance to it (m).

    Uses a flat local projection (metres east/north of the point), which is accurate to
    well under a metre over the few hundred metres that matter here.
    """
    kx = 111320 * math.cos(math.radians(lat))      # metres per degree of longitude
    ky = 110540                                    # metres per degree of latitude
    xs = [(x - lon) * kx for x in cl.lon]
    ys = [(y - lat) * ky for y in cl.lat]
    best = (math.inf, 0.0)
    for i in range(len(xs) - 1):
        ax, ay, bx, by = xs[i], ys[i], xs[i + 1], ys[i + 1]
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        # t: how far along the segment the nearest point is, 0..1
        t = 0.0 if seg2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg2))
        d = math.hypot(ax + t * dx, ay + t * dy)
        if d < best[0]:
            ch = cl.chainage_km.iloc[i] + t * (cl.chainage_km.iloc[i + 1] - cl.chainage_km.iloc[i])
            best = (d, ch)
    return best[1], best[0]


def download_gauges():
    """Make data/gauges.csv from the council's gauge list and the centreline."""
    ids = ", ".join(f'"{g}"' for g in BCC_GAUGES)
    url = f"{METADATA_URL}?{urllib.parse.urlencode({'where': f'sensor_id in ({ids})'})}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        meta = {r["sensor_id"]: r for r in json.load(resp)}
    missing = set(BCC_GAUGES) - set(meta)
    if missing:
        raise SystemExit(f"Not in the council's gauge list: {sorted(missing)}")
    cl = pd.read_csv(DATA / "centreline.csv")
    rows = []
    for g in BCC_GAUGES:                         # downstream to upstream
        m = meta[g]
        ch, off = project_onto(cl, m["longitude"], m["latitude"])
        rows.append({"sensor_id": g, "bom_no": m["location_id"], "name": m["location_name"],
                     "short": SHORT[g], "lat": m["latitude"], "lon": m["longitude"],
                     "datum": m["sensor_type"], "unit": m["unit_of_measure"],
                     "chainage_km": round(ch, 2), "offset_m": round(off)})
    with GAUGES_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(f'{r["sensor_id"]} {r["short"]:13} km {r["chainage_km"]:6.2f}, '
              f'{r["offset_m"]:4} m from the centreline')
    print("Wrote", GAUGES_CSV)


# Colleges Crossing (BoM 540063, km 83.81), above Kholo Creek. Not in the council's data:
# its readings are BoM's, saved on the gauge-data branch (bom/ by the 15-minute
# collection, bom-filled/ read by hand from BoM's web table), which the page fetches from
# GitHub (raw.githubusercontent.com allows that from any page). They are m AHD (gauge
# zero 0.00 AHD), so they sit on the same datum as the council's.
BOM_GAUGE = {
    "id": "540063", "bom": "540063", "name": "Brisbane River at Colleges Crossing",
    "short": "Colleges Crossing", "feature_id": "gauge-colleges-crossing",
    # Reads nothing below this (BoM): 0.59 means "here or lower".
    "floor_m": 0.59,
    # It reports each 0.05 m change, plus a reading about every 3 hours when the level
    # holds, so a quiet spell of up to 3 hours means "no change", not "no reading".
    "gap_max_min": 180,
}
BOM_FILES = "https://raw.githubusercontent.com/RowanP4069/Brisbane-River-tides/gauge-data/"
KM_SHOWN = 85.0               # the page shows the river to here (past Colleges Crossing)


def bom_gauge():
    """The Colleges Crossing entry for the page, placed from data/features.csv."""
    f = pd.read_csv(DATA / "features.csv").set_index("feature_id").loc[BOM_GAUGE["feature_id"]]
    g = {k: v for k, v in BOM_GAUGE.items() if k != "feature_id"}
    g.update(lon=float(f.lon), lat=float(f.lat), chainage_km=float(f.km), source="bom")
    return g


def build_payload(built=None):
    g = pd.read_csv(GAUGES_CSV, dtype={"bom_no": str})
    if not g.chainage_km.is_monotonic_increasing:
        raise SystemExit(f"{GAUGES_CSV}: gauges must be listed downstream to upstream")
    st = load_stations(DATA / "stations.csv")
    cl = pd.read_csv(DATA / "centreline.csv")
    kholo_km = float(st.chainage_km.max())                   # MSQ's figures end here
    river = cl[cl.chainage_km <= KM_SHOWN + 0.5]
    meta = {
        "source": ("https://data.brisbane.qld.gov.au/api/explore/v2.1/catalog/datasets/"
                   "telemetry-sensors-rainfall-and-stream-heights-observations/exports/json"),
        "timezone": "AEST (UTC+10)",
        "datum": "metres AHD (as published by Brisbane City Council)",
        "km_max": KM_SHOWN,
        "kholo_km": kholo_km,
        # BoM gauge files on the gauge-data branch: the hand-filled series, and the
        # 15-minute collection's monthly files (bom/YYYY-MM.csv).
        "bom": {"base": BOM_FILES, "filled": "bom-filled/{id}.csv", "monthly": "bom/{month}.csv"},
    }
    if built is not None:
        meta["built"] = built.strftime("%Y-%m-%dT%H:%M")
    return {
        "meta": meta,
        # Downstream to upstream; Colleges Crossing last.
        "gauges": [{"id": r.sensor_id, "bom": r.bom_no, "name": r["name"], "short": r.short,
                    "lon": r.lon, "lat": r.lat, "chainage_km": r.chainage_km, "source": "bcc"}
                   for _, r in g.iterrows()] + [bom_gauge()],
        "stations": station_labels(st, DATA / "centreline.csv"),
        "river": {"lon": river.lon.round(5).tolist(), "lat": river.lat.round(5).tolist()},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--download", action="store_true",
                    help="remake data/gauges.csv from the council's gauge list first")
    ap.add_argument("--out", default=str(HERE / "output" / "gauges.html"),
                    help="page to write (default: output/gauges.html)")
    ap.add_argument("--template", default=str(HERE / "web" / "gauges_template.html"))
    ap.add_argument("--stamp", action="store_true",
                    help="show on the page when it was built (AEST)")
    args = ap.parse_args()

    if args.download:
        download_gauges()
    built = pd.Timestamp.now(tz=BRISBANE).tz_localize(None) if args.stamp else None
    html = Path(args.template).read_text(encoding="utf-8")
    marker = "/*__DATA__*/null"
    if html.count(marker) != 1:
        raise SystemExit(f"Template must contain {marker} exactly once: {args.template}")
    data = to_json(build_payload(built)).replace("</", "<\\/")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(html.replace(marker, data), encoding="utf-8")
    print("Wrote", args.out)


if __name__ == "__main__":
    main()
