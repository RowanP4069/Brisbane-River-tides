#!/usr/bin/env python3
"""Check that the page's JavaScript model gives the same heights as river_tides.py.

The page works out heights itself for whichever day the viewer picks (the "Model"
block in web/predictions_template.html). Python stays the source of truth: for each
test window this script

  1. runs river_tides.py --json to get Python's heights for that window, and
  2. runs the template's Model block in Node on the same data,

and compares them. Python's heights are rounded to 1 mm, so the page must agree to
within half a millimetre (plus float noise).

Windows tested: ordinary days in different months, a big spring tide, across New
Year, the first and last days the page offers, and a start time that isn't midnight.

Usage:
  python check_parity.py            # needs node on the PATH; exits non-zero on a mismatch

Run it after changing the model in either river_tides.py or the template.

It also checks the report page (web/report_template.html): its heightAt(km, time), used
for the verdict, must match river_tides.heights() at a spread of places and times.

And it checks the measured-vs-predicted page (web/compare_template.html): run over all
the readings, the page's Stats block must give the same statistics as compare_gauges.py.
That part needs the gauge-data branch (git fetch origin gauge-data) and is skipped,
with a note, without it.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
TEMPLATE = HERE / "web" / "predictions_template.html"
COMPARE_TEMPLATE = HERE / "web" / "compare_template.html"
REPORT_TEMPLATE = HERE / "web" / "report_template.html"
GAUGE_REF = "origin/gauge-data"
TOLERANCE_M = 0.0005 + 1e-9         # Python rounds to 1 mm

# (start, hours): start as for river_tides.py --start
WINDOWS = [
    ("2026-01-02", 48),             # first day the page offers (Jan 1 lacks upstream lag)
    ("2026-03-17", 24),
    ("2026-06-30", 48),
    ("2026-11-08", 48),
    ("2026-12-31", 48),             # across New Year (two Bar files)
    ("2027-01-01T06:30", 24),       # start time that isn't midnight
    ("2027-09-12", 48),
    ("2027-12-29", 48),             # last 48 h window (to 31 Dec 00:00; the data ends 23:50)
]

# Runs the template's Model block with the payload, then prints the window as JSON.
NODE_RUNNER = """
const fs = require("fs");
const DATA = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
eval(fs.readFileSync(process.argv[3], "utf8"));
const startMs = isoMs(DATA.meta.start), out = computeWindow(startMs, DATA.meta.hours, DATA.meta.step_min);
process.stdout.write(JSON.stringify(out));
"""


def model_block(template=TEMPLATE, name="Model"):
    """The JavaScript between the BEGIN and END markers called name in the template."""
    html = template.read_text(encoding="utf-8")
    m = re.search(rf"// ---- {name}: BEGIN.*?\n(.*?)// ---- {name}: END", html, re.S)
    if not m:
        raise SystemExit(f"{name} BEGIN/END markers not found in {template}")
    # Top-level const/let would be scoped to eval() and invisible after it; var isn't.
    return re.sub(r"^(const|let) ", "var ", m.group(1), flags=re.M)


# Runs the compare page's Stats block over all the readings, prints the stats as JSON.
STATS_RUNNER = """
const fs = require("fs");
const DATA = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
eval(fs.readFileSync(process.argv[3], "utf8"));
const out = {};
for (const g of DATA.gauges) out[g.id] = windowStats(g, -Infinity, Infinity);
process.stdout.write(JSON.stringify(out));
"""

# Allowed differences, page vs Python. Events reach the page rounded: heights to 1 mm,
# range ratios to 4 decimals. Everything else is the same arithmetic.
STATS_TOL = {"hw_dh_m": 0.0005, "lw_dh_m": 0.0005, "range_ratio": 0.0001}
STATS_KEYS = ["readings", "bar_mean_resid_m", "rms_m", "p95_abs_m", "max_abs_m",
              "n_hw", "hw_dt_min", "hw_dt_sd", "n_lw", "lw_dt_min", "lw_dt_sd",
              "hw_dh_m", "lw_dh_m", "n_range", "range_ratio",
              "meas_hw_lag_min", "meas_lw_lag_min"]


def check_compare(tmp):
    """Compare page statistics vs compare_gauges.py over all readings. Returns failures."""
    have = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--verify", "-q", GAUGE_REF],
                          capture_output=True).returncode == 0
    if not have:
        print(f"Compare page: SKIPPED, no {GAUGE_REF} (git fetch origin gauge-data)")
        return []
    (tmp / "stats.js").write_text(model_block(COMPARE_TEMPLATE, "Stats"), encoding="utf-8")
    (tmp / "stats_runner.js").write_text(STATS_RUNNER, encoding="utf-8")
    data = tmp / "compare.json"
    subprocess.run([sys.executable, str(HERE / "compare_gauges.py"), "--ref", GAUGE_REF,
                    "--json", str(data), "--out", str(tmp / "compare.html"),
                    "--csv-dir", str(tmp)], check=True, capture_output=True, text=True)
    py = {s["gauge"]: s for s in json.loads(data.read_text())["summary"]}
    js = json.loads(subprocess.run(["node", str(tmp / "stats_runner.js"), str(data),
                                    str(tmp / "stats.js")],
                                   check=True, capture_output=True, text=True).stdout)
    bad = []
    for gid, s in py.items():
        for k in STATS_KEYS:
            a, b = s.get(k), js[gid].get(k)
            if a is None or b is None:
                same = a is None and b is None
            else:
                same = abs(a - b) <= STATS_TOL.get(k, 1e-9) + 1e-12 * abs(a)
            if not same:
                bad.append(f"{s['short']} {k}: python {a}, page {b}")
    for line in bad:
        print("Compare page MISMATCH:", line)
    print(f"Compare page: {len(py)} gauges x {len(STATS_KEYS)} statistics, "
          f"{'all match' if not bad else f'{len(bad)} differ'}")
    return ["compare page"] if bad else []


# Runs the report page's Model block at (km, time) pairs, prints the heights as JSON.
REPORT_RUNNER = """
const fs = require("fs");
const DATA = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
eval(fs.readFileSync(process.argv[3], "utf8"));
const q = JSON.parse(fs.readFileSync(process.argv[4], "utf8"));
process.stdout.write(JSON.stringify(q.map(([km, t]) => heightAt(km, isoMs(t)))));
"""


def check_report(tmp):
    """Report page heightAt() vs river_tides.heights(). Returns failures."""
    import numpy as np
    import pandas as pd
    sys.path.insert(0, str(HERE))
    import build_report
    from river_tides import DATA, add_corrections, heights, load_bars, load_stations
    payload = build_report.build_payload(today=pd.Timestamp("2026-11-09"))
    payload["reports"] = []
    (tmp / "report.json").write_text(json.dumps(payload))
    st = load_stations(DATA / "stations.csv")
    bar_msl = float(st.loc[st.chainage_km == 0, "msl_m"].iloc[0])
    bar = load_bars(sorted(DATA.glob("bar_*_10min.csv")))
    kms = [0, 3.3, 12.87, 20.44, 37.0, 44.7, 50.0, 66.8, 75.8]       # stations and between
    times = pd.date_range("2026-11-08 00:00", "2026-11-12 23:00", freq="97min")
    pts = add_corrections(pd.DataFrame({"chainage_km": kms}), st)
    py = heights(bar, times, pts, bar_msl)                             # [time, km]
    q = [[km, f"{t:%Y-%m-%dT%H:%M}"] for t in times for km in kms]
    (tmp / "q.json").write_text(json.dumps(q))
    (tmp / "report_model.js").write_text(model_block(REPORT_TEMPLATE), encoding="utf-8")
    (tmp / "report_runner.js").write_text(REPORT_RUNNER, encoding="utf-8")
    js = json.loads(subprocess.run(["node", str(tmp / "report_runner.js"), str(tmp / "report.json"),
                                    str(tmp / "report_model.js"), str(tmp / "q.json")],
                                   check=True, capture_output=True, text=True).stdout)
    worst = float(np.max(np.abs(np.array(js) - py.ravel())))
    ok = worst <= 1e-9
    print(f"Report page: {len(js)} heights, largest difference {worst:.1e} m  "
          f"{'ok' if ok else 'MISMATCH'}")
    return [] if ok else ["report page"]


def main():
    worst_all = 0.0
    failed = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "model.js").write_text(model_block(), encoding="utf-8")
        (tmp / "runner.js").write_text(NODE_RUNNER, encoding="utf-8")
        for start, hours in WINDOWS:
            data = tmp / "data.json"
            subprocess.run([sys.executable, str(HERE / "river_tides.py"), "--start", start,
                            "--hours", str(hours), "--json", str(data),
                            "--out", str(tmp / "page.html")],
                           check=True, capture_output=True, text=True)
            py = json.loads(data.read_text())
            js = json.loads(subprocess.run(["node", str(tmp / "runner.js"), str(data),
                                            str(tmp / "model.js")],
                                           check=True, capture_output=True, text=True).stdout)
            if js["times"] != py["times"]:
                failed.append(start)
                print(f"{start:17} {hours} h: FRAME TIMES DIFFER "
                      f"(py {py['times'][0]}..{py['times'][-1]}, "
                      f"js {js['times'][0]}..{js['times'][-1]})")
                continue
            pairs = [(a, b) for rp, rj in zip(py["heights"], js["heights"])
                     for a, b in zip(rp, rj)]
            worst = max(abs(a - b) for a, b in pairs)
            # Also round the page's values the way Python does: ideally identical; a
            # value sitting on a half-millimetre can round either way.
            n_round = sum(1 for a, b in pairs if round(b, 3) != a)
            worst_all = max(worst_all, worst)
            ok = worst <= TOLERANCE_M
            if not ok:
                failed.append(start)
            print(f"{start:17} {hours} h: {len(pairs):6} heights, largest difference "
                  f"{worst * 1000:.3f} mm, {n_round} differ after rounding to 1 mm  "
                  f"{'ok' if ok else 'MISMATCH'}")
        failed += check_compare(tmp)
        failed += check_report(tmp)
    print(f"Largest difference overall: {worst_all * 1000:.3f} mm "
          f"(allowed {TOLERANCE_M * 1000:.1f} mm: Python rounds to 1 mm)")
    if failed:
        raise SystemExit(f"Mismatch in: {', '.join(failed)}")
    print("Page model matches river_tides.py.")


if __name__ == "__main__":
    main()
