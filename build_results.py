#!/usr/bin/env python3
"""Build the "Report the flow (results)" page (output/results.html, results.html on the website).

Everything seen on the river so far, in one place:
  - every accepted flow report (the reports branch), with its verdict worked out again
    against the current model, so the match rate tracks the model as it improves
  - the project's own field observations (data/observations.csv) and the features
    they refer to (data/features.csv)
  - a summary by reach: how many reports, from how many devices, and how many matched
  - the hypotheses above Kholo Creek (docs/hypotheses.md) with their running tallies

Verdicts are worked out as the report page does at the moment of sending (its
tideState() and verdictFor()), in Python here. The build prints any report whose
verdict now differs from the one the reporter was shown.

Usage:
  python build_results.py                                  # write output/results.html
  python build_results.py --stamp --out site/results.html  # as the website is built
"""
import argparse
import csv
import io
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from build_report import REPORT_KM_MAX, REPORTS_REF
from river_tides import BRISBANE, DATA, HERE, load_bars, load_stations, station_labels, to_json, write_html

TURN_MIN = 45              # as the report page: within this of high/low water = "near the turn"
SCAN_H = 8                 # look this far either side for the nearest high or low water
PCT_MIN = 5                # show a percentage once a reach has this many checkable reports
INDOOROOPILLY_KM = 37.6    # last station with an MSQ published ratio (stations.csv)
# H1 (docs/hypotheses.md): high water above Kholo comes 1 to 3 min per km later than
# MSQ's Kholo high water (150 min after the Bar's), up to km 83.7; 10 min allowance.
H1 = {"id": "H1", "from_km": 75.8, "to_km": 83.7, "base_min": 150, "lo_per_km": 1.0,
      "hi_per_km": 3.0, "allow_min": 10, "since": "2026-11-14"}


# --- The model, as the report page's heightAt() and tideState() --------------------

class Model:
    def __init__(self, st, bar):
        self.st = st
        self.bar_msl = float(st.loc[st.chainage_km == 0, "msl_m"].iloc[0])
        self.km_max = float(st.chainage_km.max())
        self.t0 = bar.index[0]
        self.bar_x = ((bar.index - self.t0) / pd.Timedelta(minutes=1)).to_numpy(float)
        self.bar_y = bar.to_numpy(float) - self.bar_msl

    def minutes(self, t):
        return (pd.Timestamp(t) - self.t0) / pd.Timedelta(minutes=1)

    def height(self, km, m):
        """Height at km for times m (minutes from t0); NaN outside the Bar data."""
        st = self.st
        lag = np.interp(km, st.chainage_km, st.lag_min)
        ratio = np.interp(km, st.chainage_km, st.ratio)
        msl = np.interp(km, st.chainage_km, st.msl_m)
        x = np.asarray(m, float) - lag
        a = np.interp(x, self.bar_x, self.bar_y, left=np.nan, right=np.nan)
        return msl + ratio * a

    def turns(self, km, m):
        """Local highs and lows within SCAN_H hours of m, scanned every 2 min:
        [(kind, minutes)], as the page's tideState()."""
        ts = m + np.arange(-SCAN_H * 60, SCAN_H * 60 + 1, 2, dtype=float)
        hs = self.height(km, ts)
        out = []
        for i in range(1, len(hs) - 1):
            if hs[i] > hs[i - 1] and hs[i] >= hs[i + 1]:
                out.append(("high", ts[i]))
            elif hs[i] < hs[i - 1] and hs[i] <= hs[i + 1]:
                out.append(("low", ts[i]))
        return out

    def state(self, km, t):
        """{rising, turn kind, minutes from the turn} at km and time t, or None."""
        m = self.minutes(t)
        d = self.height(km, m + 5) - self.height(km, m - 5)
        if not np.isfinite(d):
            return None
        turns = self.turns(km, m)
        turn = min(turns, key=lambda k: abs(k[1] - m)) if turns else None
        return {"rising": bool(d > 0), "turn": turn[0] if turn else None,
                "min_from_turn": (m - turn[1]) if turn else None}

    def bar_hw_offset(self, t):
        """Minutes after the nearest predicted high water at the Bar (negative: before)."""
        m = self.minutes(t)
        highs = [x for k, x in self.turns(0.0, m) if k == "high"]
        if not highs:
            return None
        return round(m - min(highs, key=lambda x: abs(x - m)), 1)


def verdict(model, dir_, km, t):
    """("match" | "turn" | "mismatch" | "none", why), as the page's verdictFor()."""
    if km > model.km_max + 0.2:
        return "none", "above"
    st = model.state(km, t)
    if st is None:
        return "none", "no_data"
    if st["turn"] and abs(st["min_from_turn"]) <= TURN_MIN:
        return "turn", ""
    if dir_ == "swirl":
        return "none", "swirl"
    return ("match" if dir_ == ("up" if st["rising"] else "down") else "mismatch"), ""


# --- Inputs ------------------------------------------------------------------------

def all_reports(ref=REPORTS_REF):
    """Every accepted report on the reports branch, oldest first; [] if none."""
    try:
        names = subprocess.run(["git", "-C", str(HERE), "ls-tree", "--name-only", f"{ref}:reports"],
                               check=True, capture_output=True, text=True).stdout.split()
    except subprocess.CalledProcessError:
        print(f"No reports in {ref}: the page shows none")
        return []
    rows = []
    for n in sorted(names):
        text = subprocess.run(["git", "-C", str(HERE), "show", f"{ref}:reports/{n}"],
                              check=True, capture_output=True, text=True).stdout
        rows += list(csv.DictReader(io.StringIO(text)))
    return sorted(rows, key=lambda r: r["time_aest"])


def reaches(st, features):
    """Reaches mouth to ruin: between stations up to Kholo, then between gravel runs.
    Each has a zone: "msq" (published ratios), "msq_sn" (spring/neap figures), "hyp"."""
    out = []
    for a, b in zip(st.itertuples(), st.iloc[1:].itertuples()):
        out.append({"from_km": a.chainage_km, "to_km": b.chainage_km,
                    "name": f"{a.name.split(' (')[0]} to {b.name.split(' (')[0]}",
                    "zone": "msq" if b.chainage_km <= INDOOROOPILLY_KM else "msq_sn"})
    runs = features[features.kind == "gravel run"].sort_values("km")
    marks = [(float(st.chainage_km.max()), "Kholo Creek")]
    marks += [(float(r.km), r.name) for r in runs.itertuples() if r.km < REPORT_KM_MAX]
    marks += [(REPORT_KM_MAX, "Old weir ruin")]
    for (a, an), (b, bn) in zip(marks, marks[1:]):
        out.append({"from_km": a, "to_km": b, "name": f"{an} to {bn}", "zone": "hyp"})
    return out


def reach_of(rs, km):
    for i, r in enumerate(rs):
        if km <= r["to_km"] + 1e-9:
            return i
    return len(rs) - 1


def matched_words(m, n):
    if n == 0:
        return ""
    if n < PCT_MIN:
        return f"{m} of {n}"
    return f"{round(100 * m / n)}% ({m} of {n})"


# --- The page's data ----------------------------------------------------------------

def build_payload(built=None, reports_ref=REPORTS_REF):
    st_all = pd.read_csv(DATA / "stations.csv")
    st = load_stations(DATA / "stations.csv")
    bar = load_bars(sorted(DATA.glob("bar_*_10min.csv")))
    model = Model(st, bar)
    features = pd.read_csv(DATA / "features.csv")
    obs = pd.read_csv(DATA / "observations.csv", dtype=str).fillna("")
    cl = pd.read_csv(DATA / "centreline.csv")
    river = cl[cl.chainage_km <= REPORT_KM_MAX + 0.5]
    rs = reaches(st, features)

    reports, changed = [], 0
    for r in all_reports(reports_ref):
        t = pd.Timestamp(r["time_aest"])
        km = float(r["km"])
        v, why = verdict(model, r["dir"], km, t)
        if v != r["verdict"]:
            changed += 1
            print(f"Verdict now {v}, was {r['verdict']}: {r['time_aest']} km {km} {r['dir']}")
        reports.append({"time": r["time_aest"], "km": km, "bank": r["bank"], "alias": r["alias"],
                        "dir": r["dir"], "strength": int(r["strength"]) if r["strength"] else None,
                        "clarity": int(r["clarity"]) if r["clarity"] else None,
                        "problems": r["problems"], "verdict": v, "why": why,
                        "sent_verdict": r["verdict"], "device": r["device"],
                        "reach": reach_of(rs, km), "bar_hw_min": model.bar_hw_offset(t)})

    fnames = dict(zip(features.feature_id, features.name))
    observations = []
    for o in obs.itertuples():
        a, b = float(o.km_from), float(o.km_to)
        t0, t1 = pd.Timestamp(o.time_from_aest), pd.Timestamp(o.time_to_aest)
        x0, x1 = model.bar_hw_offset(t0), model.bar_hw_offset(t1)
        observations.append({
            "id": o.obs_id, "from": o.time_from_aest, "to": o.time_to_aest,
            "feature": fnames.get(o.feature_id, ""), "km": round((a + b) / 2, 2),
            "km_from": a, "km_to": b, "quantity": o.quantity, "value": o.value,
            "confidence": o.confidence, "kholo_min": o.kholo_min_m, "kholo_max": o.kholo_max_m,
            "reach": reach_of(rs, (a + b) / 2),
            # The span on the chart, only when both ends are in the Bar data and on the
            # same side of one high water.
            "bar_hw_min": [x0, x1] if x0 is not None and x1 is not None and x0 <= x1 else None})

    # By reach: counts, devices (a blank device counts as its own), days.
    for i, r in enumerate(rs):
        mine = [p for p in reports if p["reach"] == i]
        devs = {p["device"] or f"blank{j}" for j, p in enumerate(mine)}
        c = {k: sum(p["verdict"] == k for p in mine) for k in ("match", "turn", "mismatch")}
        c["none"] = len(mine) - sum(c.values())
        n = c["match"] + c["mismatch"]
        r.update({"reports": len(mine), "devices": len(devs),
                  "days": len({p["time"][:10] for p in mine}), **c,
                  "matched": matched_words(c["match"], n),
                  "observations": sum(o["reach"] == i for o in observations)})

    # H1 tests: observations of the time of high water, made on or after H1's date.
    tests = []
    for o in obs.itertuples():
        if o.quantity != "high_water_time" or o.confidence == "excluded" or o.time_from_aest[:10] < H1["since"]:
            continue
        km = float(o.km_from)
        if not H1["from_km"] <= km <= H1["to_km"]:
            continue
        x = model.bar_hw_offset(pd.Timestamp(o.value))
        d = km - H1["from_km"]
        lo, hi = H1["base_min"] + H1["lo_per_km"] * d, H1["base_min"] + H1["hi_per_km"] * d
        ok = x is not None and lo - H1["allow_min"] <= x <= hi + H1["allow_min"]
        tests.append({"time": o.value, "km": km, "bar_hw_min": x, "lo": lo, "hi": hi,
                      "result": "for" if ok else "against"})

    hw = st_all.dropna(subset=["chainage_km", "lag_hw_min"]).drop_duplicates("chainage_km")
    meta = {"km_max": model.km_max, "report_km_max": REPORT_KM_MAX, "indooroopilly_km": INDOOROOPILLY_KM,
            "turn_min": TURN_MIN, "pct_min": PCT_MIN, "changed": changed}
    if built is not None:
        meta["built"] = built.strftime("%Y-%m-%dT%H:%M")
    return {
        "meta": meta,
        "river": {"lon": river.lon.round(6).tolist(), "lat": river.lat.round(6).tolist(),
                  "km": river.chainage_km.round(4).tolist()},
        "stations": station_labels(st, DATA / "centreline.csv"),
        # MSQ's high-water lags, for the chart's predicted high water line.
        "hw_line": {"km": hw.chainage_km.tolist(), "min": hw.lag_hw_min.tolist()},
        "features": features[["feature_id", "kind", "name", "km", "lat", "lon"]].to_dict("records"),
        "reaches": rs,
        "reports": reports,
        "observations": observations,
        "h1": dict(H1, tests=tests),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(HERE / "output" / "results.html"),
                    help="page to write (default: output/results.html; results.html on the website)")
    ap.add_argument("--template", default=str(HERE / "web" / "results_template.html"),
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
    print(f"Wrote {args.out} ({len(payload['reports'])} reports, "
          f"{len(payload['observations'])} field observations, "
          f"{payload['meta']['changed']} verdict(s) changed since sending)")
    if args.json:
        Path(args.json).write_text(to_json(payload))


if __name__ == "__main__":
    main()
