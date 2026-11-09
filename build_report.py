#!/usr/bin/env python3
"""Build the "Report the flow" page (output/report.html, report.html on the website).

Kayakers and others on the river report which way the water is flowing, how strongly,
and how the water looks. The page sends each report to a Google Form, then at once
compares it with the model (the same formula as the predictions page) and says whether
it matches. collect_reports.py later copies accepted reports to the reports branch, and
the next build shows the last REPORT_DAYS days of them on the page's map.

What this script puts in the page:
  - the model: Bar predictions from REPORT_BAR_BEFORE before today to REPORT_BAR_AFTER
    after it (reports can be up to 2 days old; the margin covers a few missed builds),
    and the stations' chainage, lag, ratio and MSL, which the page interpolates at the
    reported place as river_tides.add_corrections() does
  - the river centreline, to snap a pin to the river and give its chainage
  - the Google Form's address and field names (FORM below)
  - recent reports from the reports branch, if it can be read

Usage:
  python build_report.py                                  # write output/report.html
  python build_report.py --stamp --out site/report.html   # as the website is built

Privacy: the published part of a report gives the place as km along the river and which
bank, not the pin's coordinates (see collect_reports.py and data/README.md).
"""
import argparse
import csv
import io
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from river_tides import (BRISBANE, DATA, HERE, load_bars, load_stations, station_labels,
                         to_json, write_html)

# The Google Form the page posts to. The page sends two answers: "report", the part that
# is published (JSON, see the page's buildReport()), and "private", which stays in the
# form's own sheet (exact position and notes). Empty action = not connected: the page
# still works and gives its verdict, but says the report wasn't sent.
# The form "Brisbane River flow reports" and its sheet "... (responses)" are in the
# project owner's Google Drive (made 2026-11-09). Only the sheet's "public" tab
# (timestamp + report) is published; see collect_reports.py.
FORM = {
    "action": ("https://docs.google.com/forms/d/e/"
               "1FAIpQLSc8ZxLPodpPoqbuS8zEGNjmZST4Zvy_3jZ42CWEjcybiE0kig/formResponse"),
    "report": "entry.760987619",
    "private": "entry.1201707450",
}

REPORT_BAR_BEFORE = pd.Timedelta(days=3)
REPORT_BAR_AFTER = pd.Timedelta(days=30)
REPORT_DAYS = 30                  # recent reports shown on the map
MAX_OFF_M = 350                   # a pin further than this from the centreline is refused.
                                  # Not 150: the river is ~300 m wide in the city, and the
                                  # council gauges on its banks are 105-279 m from the line.
REPORTS_REF = "origin/reports"


def recent_reports(today, ref=REPORTS_REF):
    """Accepted reports from the last REPORT_DAYS days, newest first; [] if none or no
    reports branch (git fetch origin reports to get it)."""
    try:
        names = subprocess.run(["git", "-C", str(HERE), "ls-tree", "--name-only",
                                f"{ref}:reports"], check=True, capture_output=True,
                               text=True).stdout.split()
    except subprocess.CalledProcessError:
        print(f"No {ref}: the page shows no past reports")
        return []
    since = (today - pd.Timedelta(days=REPORT_DAYS)).strftime("%Y-%m-%d")
    out = []
    for n in sorted(names, reverse=True)[:2]:             # this month and last
        text = subprocess.run(["git", "-C", str(HERE), "show", f"{ref}:reports/{n}"],
                              check=True, capture_output=True, text=True).stdout
        for r in csv.DictReader(io.StringIO(text)):
            if r["time_aest"][:10] >= since:
                out.append({"time": r["time_aest"], "km": float(r["km"]), "bank": r["bank"],
                            "alias": r["alias"], "dir": r["dir"], "strength": int(r["strength"]),
                            "verdict": r["verdict"]})
    return sorted(out, key=lambda r: r["time"], reverse=True)


def build_payload(built=None, today=None, reports_ref=REPORTS_REF):
    today = today or pd.Timestamp.now(tz=BRISBANE).tz_localize(None).normalize()
    st = load_stations(DATA / "stations.csv")
    bar_msl = float(st.loc[st.chainage_km == 0, "msl_m"].iloc[0])
    bar = load_bars(sorted(DATA.glob("bar_*_10min.csv")))
    b = bar[today - REPORT_BAR_BEFORE: today + REPORT_BAR_AFTER]
    if b.empty:
        raise SystemExit("No Bar predictions around today: add the year's file (fetch_bar.py)")
    km_max = float(st.chainage_km.max())                  # Kholo Creek: the model's end
    cl = pd.read_csv(DATA / "centreline.csv")
    river = cl[cl.chainage_km <= km_max + 0.5]
    meta = {"km_max": km_max, "max_off_m": MAX_OFF_M, "report_days": REPORT_DAYS,
            "timezone": "AEST (UTC+10)"}
    if built is not None:
        meta["built"] = built.strftime("%Y-%m-%dT%H:%M")
    return {
        "meta": meta,
        "form": FORM,
        "model": {
            "bar_start": b.index[0].strftime("%Y-%m-%dT%H:%M"), "bar_step_min": 10,
            "bar_mm": np.round(b.values * 1000).astype(int).tolist(), "bar_msl_m": bar_msl,
            # Stations, mouth to upstream, for interpolation along the river.
            "km": st.chainage_km.tolist(), "lag_min": st.lag_min.tolist(),
            "ratio": st.ratio.tolist(), "msl_m": st.msl_m.tolist(),
        },
        "stations": station_labels(st, DATA / "centreline.csv"),
        "river": {"lon": river.lon.round(6).tolist(), "lat": river.lat.round(6).tolist(),
                  "km": river.chainage_km.round(4).tolist()},
        "reports": recent_reports(today, reports_ref),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(HERE / "output" / "report.html"),
                    help="page to write (default: output/report.html; report.html on the website)")
    ap.add_argument("--template", default=str(HERE / "web" / "report_template.html"),
                    help="page template with the /*__DATA__*/null marker (default: web/)")
    ap.add_argument("--json", help="also write the page data to this JSON file")
    ap.add_argument("--reports-ref", default=REPORTS_REF,
                    help=f"git ref with the accepted reports (default: {REPORTS_REF})")
    ap.add_argument("--stamp", action="store_true",
                    help="show on the page when it was built (AEST); the website uses it")
    args = ap.parse_args()
    built = pd.Timestamp.now(tz=BRISBANE).tz_localize(None) if args.stamp else None
    payload = build_payload(built, reports_ref=args.reports_ref)
    write_html(payload, args.template, args.out)
    print(f"Wrote {args.out} ({len(payload['reports'])} recent reports, "
          f"form {'connected' if FORM['action'] else 'NOT connected'})")
    if args.json:
        Path(args.json).write_text(to_json(payload))


if __name__ == "__main__":
    main()
