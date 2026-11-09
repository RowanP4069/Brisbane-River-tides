#!/usr/bin/env python3
"""Compare measured water levels with the model's predictions: the compare.html page.

Reads the readings collect_gauges.py saves on the gauge-data branch, works out what
river_tides.py predicts at each gauge for the same times, and reports how well they
agree, as a page (compare.html on the website) where any period can be picked, plus a
printed summary and CSVs. The results feed roadmap decisions 4 (separate HW/LW lags)
and 5 (ratio varying spring <-> neap); nothing here changes the model.

Python does all the fitting, once, over all the readings: the datum offset, gauge
floors, and the timing and height of each high and low water. The page only picks out
the readings and events in the chosen period and averages them (the Stats block in
web/compare_template.html; check_parity.py checks it matches this script's summary).

Gauges: the MSQ Brisbane Bar gauge (metres above LAT) and Brisbane City Council's
eight river gauges (metres AHD, positions from data/gauges.csv). The model is
applied at each gauge's chainage exactly as on the predictions page.

Datum: council gauges read AHD, the model gives local LAT, and the gap between the
two differs along the river. So for each council gauge the script FITS the offset
(the mean of measured minus predicted) and reports it, rather than assuming one.
That offset also absorbs any average weather or freshwater effect over the period;
the Bar row (same datum both sides, offset not fitted) shows how big that is.

What it measures, per gauge:
  - height residual (measured - predicted - offset): RMS, 95th percentile, worst
  - timing error at each high and low water, separately (measured minus predicted,
    minutes; positive = the river turned later than predicted). Item 4.
  - height error at each high and low water.
  - range of each rise or fall, measured / predicted, against the predicted range
    (big = spring, small = neap). Item 5; needs a spring-neap cycle (~15 days).

Timing a high or low water (see match_events): the council gauges report only when
the level has moved a step (1, 2 or 5 cm depending on the gauge), so near the turn
there are few readings. Instead the predicted curve within SEARCH_MIN of the turn is
shifted in time to fit the readings, using the busy rise and fall either side.
Tested on made-up data with known shifts (2026-11-09):
  - 5 cm steps make the river look about 3 minutes early; 1-2 cm steps, under 1.
    The step size is in the report; City Gauge (1 cm) is the cleanest timing.
  - the fit sees the upper (or lower) part of the curve, not only the turn, so a
    real difference between the HW and LW lags shows up only about half as large.
    Compare HW dt with LW dt for direction, not exact size.

Gauge floors: some gauges seem unable to read below a level (sensor dry at low
water?). find_floor detects it; readings near it and the low waters it hides are
left out, and the floor is reported.

Writes (output/ is not committed):
  output/compare.html          the page (web/compare_template.html with the data inlined)
  output/compare/summary.csv   the summary table, over all the readings used
  output/compare/events.csv    every matched high and low water

Usage:
  git fetch origin gauge-data          # get the latest readings first
  python compare_gauges.py
  python compare_gauges.py --since 2026-11-10 --until 2026-11-25    # printout and CSVs
  python compare_gauges.py --stamp --out site/compare.html          # as the website is built

The Bar's 1-minute readings are thinned to every 5 minutes, like the council slots.
The page holds every reading, about 8 KB a day; at some 3 MB a year that's fine for now,
but by mid-2027 consider monthly data files the page loads as needed.

Weather, surge, wind and freshwater flow are all in the measured data and none are
in the model, so the residuals are an upper limit on the model's own error.
"""
import argparse
import io
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from river_tides import (BRISBANE, DATA, HERE, add_corrections, heights, load_bars,
                         load_stations, to_json, write_html)

BAR_GAUGE = "046046A"           # MSQ station number for Brisbane Bar (collect_gauges.py)

# Finding high and low water (minutes).
SEARCH_MIN = 120     # readings within this of a predicted high or low water are fitted
                     # (narrower: closer to the turn but too few readings at 5 cm gauges)
MAX_SHIFT_MIN = 90   # largest timing error tried
MIN_READINGS = 12    # readings needed in that window
FIT_HALF_MIN = 60    # predicted extreme: quadratic fitted within this of the top sample
MIN_SIDE = 3         # readings needed on each side of the turn
PAIR_MAX_H = 9       # a rise or fall longer than this means a turning point is missing

# Gauges that dry out at low water (see find_floor).
FLOOR_GAP_MIN = 180  # a silence at least this long...
FLOOR_MIN_TIMES = 2  # ...ending at the same level, this many times, means a floor
FLOOR_MARGIN_M = 0.05  # readings within this of the floor are left out

REF = pd.Timestamp("2026-01-01")    # times become minutes since this, for the fits


# --- Inputs ----------------------------------------------------------------------

def git(*args):
    return subprocess.run(["git", "-C", str(HERE), *args], check=True,
                          capture_output=True, text=True).stdout


def read_branch(ref, folder):
    """All monthly CSVs in folder on the branch ref, as one DataFrame (time, gauge, value_m)."""
    names = [n for n in git("ls-tree", "--name-only", f"{ref}:{folder}").split()
             if n.endswith(".csv")]
    if not names:
        raise SystemExit(f"No CSV files in {ref}:{folder}")
    df = pd.concat([pd.read_csv(io.StringIO(git("show", f"{ref}:{folder}/{n}")),
                                dtype={"gauge": str}) for n in sorted(names)])
    df["time"] = pd.to_datetime(df.time_aest, format="%Y-%m-%d %H:%M")
    return df.drop(columns="time_aest").sort_values(["gauge", "time"])


def gauge_list(stations):
    """The Bar plus the council gauges, with the model's lag, ratio and MSL at each,
    and the published HW and LW lags interpolated the same way (for comparison only)."""
    g = pd.read_csv(DATA / "gauges.csv", dtype={"sensor_id": str})
    bar = pd.DataFrame([{"sensor_id": BAR_GAUGE, "short": "Bar", "name": "Brisbane Bar",
                         "chainage_km": 0.0}])
    g = pd.concat([bar, g[["sensor_id", "short", "name", "chainage_km"]]],
                  ignore_index=True)
    add_corrections(g, stations)
    for col in ["lag_hw_min", "lag_lw_min"]:
        g[col] = np.interp(g.chainage_km, stations.chainage_km, stations[col])
    g["datum"] = np.where(g.sensor_id == BAR_GAUGE, "LAT", "AHD")
    return g


# --- High and low water ------------------------------------------------------------

def minutes(times):
    return (pd.DatetimeIndex(times) - REF).total_seconds().values / 60


def turning_points(h):
    """Indices and kinds ("HW"/"LW") of the local extremes of a smooth series."""
    d = np.diff(h)
    out = []
    for i in range(1, len(h) - 1):
        if d[i - 1] > 0 >= d[i]:
            out.append((i, "HW"))
        elif d[i - 1] < 0 <= d[i]:
            out.append((i, "LW"))
    return out


def fit_extreme(x, h, kind):
    """Time and height of high (or low) water from samples x (minutes), h (metres).

    Takes the highest (lowest) sample, after a 3-point median to ignore single spikes,
    fits a quadratic to the samples within FIT_HALF_MIN of it and returns the vertex.
    None if the samples don't pin it down: too few each side, the extreme sample at
    the edge of the search window, or the fitted curve the wrong way up.
    """
    if len(x) < 2 * MIN_SIDE + 1:
        return None
    smooth = pd.Series(h).rolling(3, center=True, min_periods=1).median().values
    j = int(np.argmax(smooth) if kind == "HW" else np.argmin(smooth))
    if x[j] - x[0] < 10 or x[-1] - x[j] < 10:
        return None                         # extreme is at the window edge, or beyond
    near = np.abs(x - x[j]) <= FIT_HALF_MIN
    xs, hs = x[near] - x[j], h[near]
    if (xs < 0).sum() < MIN_SIDE or (xs > 0).sum() < MIN_SIDE:
        return None
    a, b, c = np.polyfit(xs, hs, 2)
    if (kind == "HW") != (a < 0):
        return None
    v = -b / (2 * a)
    if abs(v) > FIT_HALF_MIN:
        return None
    return x[j] + v, c - b * b / (4 * a)


def fit_shift(gx, gh, mx, mh):
    """Best time shift tau (minutes) and a, b such that mh ~ a + b * pred(mx - tau).

    gx, gh: predicted heights every minute; mx, mh: readings around one high or low
    water. Tries every whole minute of shift up to MAX_SHIFT_MIN and keeps the one with
    the smallest squared error. None if the best shift is at the limit (no real fit).
    """
    best = None
    for tau in range(-MAX_SHIFT_MIN, MAX_SHIFT_MIN + 1):
        p = np.interp(mx - tau, gx, gh)
        b, a = np.polyfit(p, mh, 1)
        sse = float(np.sum((mh - a - b * p) ** 2))
        if best is None or sse < best[0]:
            best = (sse, tau, a, b)
    _, tau, a, b = best
    return None if abs(tau) == MAX_SHIFT_MIN else (tau, a, b)


def match_events(gid, grid_x, grid_h, mx, mh, offset, lowest=-np.inf):
    """Each predicted high and low water at a gauge, with the measured one near it.

    grid_x, grid_h: predicted heights every minute. mx, mh: measured readings.
    lowest: skip turning points predicted below this (the gauge's floor, model datum).

    The council gauges report only when the level has moved 5 cm, so near high and
    low water, where the level hardly moves, there are few readings, often none for
    an hour. So the measured turning point isn't read off the readings near the top:
    instead the predicted curve within SEARCH_MIN of it is shifted in time (and scaled)
    to fit the readings, which uses the busy rising and falling parts either side.
    Measured time = predicted time + shift; measured height = the fitted curve's
    extreme. The same method is used at the Bar (1-minute readings) for consistency.

    Returns a DataFrame, one row per turning point found in both, in time order,
    with the range of the rise or fall that ended there when the previous one matched.
    """
    rows = []
    for i, kind in turning_points(grid_h):
        tp = grid_x[i]
        win = np.abs(grid_x - tp) <= SEARCH_MIN
        p = fit_extreme(grid_x[win], grid_h[win], kind)
        win = np.abs(mx - tp) <= SEARCH_MIN
        # Enough readings, and some on both sides of the turn.
        if (p is None or p[1] < lowest or win.sum() < MIN_READINGS or (mx[win] < tp).sum() < MIN_SIDE
                or (mx[win] > tp).sum() < MIN_SIDE):
            continue
        f = fit_shift(grid_x, grid_h, mx[win], mh[win])
        if f is None:
            continue
        tau, a, b = f
        meas_h = a + b * p[1] - offset
        rows.append({"gauge": gid, "kind": kind,
                     "pred_time": p[0], "meas_time": p[0] + tau,
                     "dt_min": float(tau),
                     "pred_h": p[1], "meas_h": meas_h,
                     "dh_m": meas_h - p[1], "readings": int(win.sum())})
    ev = pd.DataFrame(rows)
    if ev.empty:
        return ev
    prev = ev.shift(1)
    ok = (prev.kind != ev.kind) & (ev.pred_time - prev.pred_time <= PAIR_MAX_H * 60)
    ev["pred_range"] = np.where(ok, (ev.pred_h - prev.pred_h).abs(), np.nan)
    ev["meas_range"] = np.where(ok, (ev.meas_h - prev.meas_h).abs(), np.nan)
    ev["range_ratio"] = ev.meas_range / ev.pred_range
    for col in ["pred_time", "meas_time"]:
        ev[col] = REF + pd.to_timedelta(ev[col], unit="min")
    return ev


# --- Analysis ----------------------------------------------------------------------

def find_floor(mx, mh):
    """The level a gauge can't read below, if it seems to have one, else None.

    Some council gauges (seen at Jindalee and Moggill) go silent for hours around
    low water and come back at the same level they left at, while the tide elsewhere
    falls and rises a metre or more: most likely the sensor sits above low water and
    dries out. Since the gauges report only on a 5 cm change, a long silence that ends
    at the same level means the reading was stuck. Floor = the highest such level,
    if it happens at least FLOOR_MIN_TIMES times.
    """
    long_gap = np.diff(mx) >= FLOOR_GAP_MIN
    same = np.abs(np.diff(mh)) <= 0.05 + 1e-9
    hits = mh[1:][long_gap & same]
    return float(hits.max()) if len(hits) >= FLOOR_MIN_TIMES else None


def analyse(row, readings, bar, bar_msl):
    """Residuals, events and plot data for one gauge."""
    r = readings[readings.gauge == row.sensor_id]
    pts = pd.DataFrame([row])[["lag_min", "ratio", "msl_m"]]
    times = pd.DatetimeIndex(r.time)
    pred = heights(bar, times, pts, bar_msl)[:, 0]
    meas = r.value_m.values
    fit = row.sensor_id != BAR_GAUGE
    floor = find_floor(minutes(times), meas) if fit else None
    # Readings at or near a floor are not real levels: leave them out of everything
    # except the plot.
    ok = meas > floor + FLOOR_MARGIN_M if floor is not None else np.ones(len(meas), bool)
    offset = float(np.mean((meas - pred)[ok])) if fit else 0.0
    resid = np.where(ok, meas - pred - offset, np.nan)

    # Margin so shifted lookups near the ends stay inside the grid.
    margin = pd.Timedelta(hours=4)
    grid = pd.date_range(times[0].floor("h") - margin, times[-1].ceil("h") + margin,
                         freq="1min")
    grid_h = heights(bar, grid, pts, bar_msl)[:, 0]
    # Below the floor (in the gauge's datum) a turning point can't be seen.
    lowest = floor + FLOOR_MARGIN_M - offset if floor is not None else -np.inf
    ev = match_events(row.sensor_id, minutes(grid), grid_h, minutes(times)[ok], meas[ok],
                      offset, lowest)

    def stats(kind, col):
        s = ev[ev.kind == kind][col] if not ev.empty else pd.Series(dtype=float)
        return s.mean(), s.std(), len(s)

    hw_dt, hw_sd, n_hw = stats("HW", "dt_min")
    lw_dt, lw_sd, n_lw = stats("LW", "dt_min")
    rr = ev.range_ratio.dropna() if not ev.empty else pd.Series(dtype=float)
    summary = {
        "gauge": row.sensor_id, "short": row.short, "chainage_km": row.chainage_km,
        "datum": row.datum, "readings": len(r),
        "first": f"{times[0]:%Y-%m-%d %H:%M}", "last": f"{times[-1]:%Y-%m-%d %H:%M}",
        # For AHD gauges: how far LAT (as the model uses it there) lies below AHD.
        "lat_below_ahd_m": -offset if fit else np.nan,
        "bar_mean_resid_m": float(np.mean(meas - pred)) if not fit else np.nan,
        "floor_m": floor if floor is not None else np.nan,
        # Smallest change between readings: the gauge's reporting step.
        "step_cm": float(np.min(d[d > 0.0005]) * 100) if len(d := np.abs(np.diff(meas))) else np.nan,
        "rms_m": float(np.sqrt(np.nanmean(resid ** 2))),
        "p95_abs_m": float(np.nanpercentile(np.abs(resid), 95)),
        "max_abs_m": float(np.nanmax(np.abs(resid))),
        "n_hw": n_hw, "hw_dt_min": hw_dt, "hw_dt_sd": hw_sd,
        "n_lw": n_lw, "lw_dt_min": lw_dt, "lw_dt_sd": lw_sd,
        "hw_dh_m": stats("HW", "dh_m")[0], "lw_dh_m": stats("LW", "dh_m")[0],
        "n_range": len(rr), "range_ratio": rr.mean(),
        "model_lag_min": row.lag_min,
        "pub_hw_lag_min": row.lag_hw_min, "pub_lw_lag_min": row.lag_lw_min,
        "meas_hw_lag_min": row.lag_min + hw_dt, "meas_lw_lag_min": row.lag_min + lw_dt,
    }
    return summary, ev, page_gauge(row, times, meas, offset, floor, summary["step_cm"], ev)


def page_gauge(row, times, meas, offset, floor, step_cm, ev):
    """One gauge's entry in the page data: model values, fitted offset and floor, the
    readings (minutes since REF as differences, whole mm), and the matched events.

    The page works out residuals and statistics for whichever window is chosen, from
    these alone (the Stats block in web/compare_template.html; check_parity.py checks
    it reproduces this script's summary over all the data).
    """
    t = np.round(minutes(times)).astype(int)
    mm = np.round(meas * 1000).astype(int)
    if np.abs(mm / 1000 - meas).max() > 1e-9:
        raise SystemExit(f"{row.sensor_id}: readings are not whole mm")
    e = ev if not ev.empty else pd.DataFrame(columns=["pred_time", "kind", "dt_min",
                                                      "dh_m", "range_ratio"])
    return {
        "id": row.sensor_id, "short": row.short, "name": row["name"],
        "km": round(float(row.chainage_km), 2), "datum": row.datum,
        # Full precision, so the page's predictions match heights() here.
        "lag_min": float(row.lag_min), "ratio": float(row.ratio), "msl_m": float(row.msl_m),
        "offset_m": offset,
        "floor_m": floor,
        # Readings at or below this are left out (None: no floor).
        "floor_cut_m": floor + FLOOR_MARGIN_M if floor is not None else None,
        "step_cm": step_cm,
        "pub_hw_lag_min": float(row.lag_hw_min), "pub_lw_lag_min": float(row.lag_lw_min),
        "t0": int(t[0]), "dt": np.diff(t).tolist(), "mm": mm.tolist(),
        "ev": {
            # Predicted time of each high/low water, whole minutes since REF: the page
            # counts an event in a window by this.
            "t": [int(round(x)) for x in minutes(e.pred_time)],
            "kind": "".join(k[0] for k in e.kind),           # "H" / "L"
            "dt": [int(x) for x in e.dt_min],                 # whole minutes already
            "dh_mm": [int(round(x * 1000)) for x in e.dh_m],
            "rr": [None if np.isnan(x) else round(float(x), 4) for x in e.range_ratio],
        },
    }


# --- Output ------------------------------------------------------------------------

def fmt(v, spec, missing="-"):
    return missing if v is None or (isinstance(v, float) and np.isnan(v)) else format(v, spec)


def print_summary(s):
    print(f"\n{'gauge':12} {'km':>5} {'n':>6} {'step':>4} {'LAT-AHD':>7} {'rms':>5} {'p95':>5}  "
          f"{'HW dt (n)':>12} {'LW dt (n)':>12} {'HW dh':>6} {'LW dh':>6} "
          f"{'range':>10}  {'lag: model':>10} {'pub HW/LW':>9} {'meas HW/LW':>10}")
    for _, r in s.iterrows():
        datum = (fmt(r.lat_below_ahd_m, ".2f") if r.datum == "AHD"
                 else f"({fmt(r.bar_mean_resid_m, '+.2f')})")
        if not np.isnan(r.floor_m):
            datum += "*"
        print(f"{r.short:12} {r.chainage_km:5.1f} {r.readings:6d} {r.step_cm:3.1f}c {datum:>7} "
              f"{r.rms_m:5.2f} {r.p95_abs_m:5.2f}  "
              f"{fmt(r.hw_dt_min, '+5.0f'):>5}±{fmt(r.hw_dt_sd, '<3.0f'):3} ({r.n_hw:d}) "
              f"{fmt(r.lw_dt_min, '+5.0f'):>5}±{fmt(r.lw_dt_sd, '<3.0f'):3} ({r.n_lw:d}) "
              f"{fmt(r.hw_dh_m, '+6.2f'):>6} {fmt(r.lw_dh_m, '+6.2f'):>6} "
              f"{fmt(r.range_ratio, '5.2f'):>5} ({r.n_range:2d})  "
              f"{r.model_lag_min:10.0f} {r.pub_hw_lag_min:4.0f}/{r.pub_lw_lag_min:<4.0f} "
              f"{fmt(r.meas_hw_lag_min, '5.0f'):>5}/{fmt(r.meas_lw_lag_min, '<4.0f')}")
    print("\nLAT-AHD: fitted, metres LAT lies below AHD (Bar: mean measured - predicted, "
          "i.e. weather).\ndt: measured minus predicted time, minutes (+ = later). "
          "dh: height error at HW/LW, m.\nrange: measured / predicted range of each rise "
          "or fall. Lags in minutes after the Bar.")
    for _, r in s[s.floor_m.notna()].iterrows():
        print(f"* {r.short}: reads no lower than about {r.floor_m:.2f} m AHD (sensor dry at "
              f"low water?); readings near it and the low waters below it are left out.")


def build_payload(gauges_page, bar, bar_msl, readings, ref, built=None):
    """Everything the page needs (becomes DATA in web/compare_template.html)."""
    first, last = readings.time.min(), readings.time.max()
    # The Bar series the page's model reads: the readings' span plus a day each side,
    # ample for the largest lag (Moggill, about 2.5 h).
    b = bar[first.floor("D") - pd.Timedelta(days=1): last.ceil("D") + pd.Timedelta(days=1)]
    bar_mm = np.round(b.values * 1000).astype(int)
    meta = {
        "ref_time": REF.strftime("%Y-%m-%dT%H:%M"),   # reading times count minutes from this
        "first_day": f"{first:%Y-%m-%d}", "last_day": f"{last:%Y-%m-%d}",
        "last_reading": f"{last:%Y-%m-%dT%H:%M}",
        "source": ref,
    }
    if built is not None:
        meta["built"] = built.strftime("%Y-%m-%dT%H:%M")
    return {
        "meta": meta,
        "model": {"bar_start": b.index[0].strftime("%Y-%m-%dT%H:%M"), "bar_step_min": 10,
                  "bar_mm": bar_mm.tolist(), "bar_msl_m": bar_msl},
        "gauges": gauges_page,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ref", default="origin/gauge-data",
                    help="git ref holding the readings (default: origin/gauge-data; "
                         "run 'git fetch origin gauge-data' first for the latest)")
    ap.add_argument("--since", help="first day to include, e.g. 2026-11-10 (AEST)")
    ap.add_argument("--until", help="last day to include, e.g. 2026-11-25 (AEST)")
    ap.add_argument("--out", default=str(HERE / "output" / "compare.html"),
                    help="page to write (default: output/compare.html; compare.html on the website)")
    ap.add_argument("--template", default=str(HERE / "web" / "compare_template.html"),
                    help="page template with the /*__DATA__*/null marker (default: web/)")
    ap.add_argument("--csv-dir", default=str(HERE / "output" / "compare"),
                    help="where to write summary.csv and events.csv (default: output/compare)")
    ap.add_argument("--json", help="also write the page data, plus this script's summary, "
                                   "to this JSON file (check_parity.py uses it)")
    ap.add_argument("--stamp", action="store_true",
                    help="show on the page when it was built (AEST); the website uses it")
    args = ap.parse_args()

    st = load_stations(DATA / "stations.csv")
    bar_msl = float(st.loc[st.chainage_km == 0, "msl_m"].iloc[0])
    bar = load_bars(sorted(DATA.glob("bar_*_10min.csv")))
    gauges = gauge_list(st)

    bar_readings = read_branch(args.ref, "msq_bar")
    # The Bar reads every minute; every 5th minute is plenty for the fits and the page,
    # and matches the council gauges' 5-minute slots.
    bar_readings = bar_readings[bar_readings.time.dt.minute % 5 == 0]
    readings = pd.concat([read_branch(args.ref, "bcc"), bar_readings])
    if args.since:
        readings = readings[readings.time >= pd.Timestamp(args.since)]
    if args.until:
        readings = readings[readings.time < pd.Timestamp(args.until) + pd.Timedelta(days=1)]
    # Keep readings the predictions cover, with a day's margin for the largest lag.
    readings = readings[(readings.time >= bar.index[0] + pd.Timedelta(days=1)) &
                        (readings.time <= bar.index[-1] - pd.Timedelta(days=1))]
    readings = readings.dropna(subset=["value_m"])

    summaries, events, page = [], [], []
    for _, g in gauges.iterrows():
        if (readings.gauge == g.sensor_id).sum() < 50:
            print(f"{g.short}: too few readings, skipped")
            continue
        s, ev, p = analyse(g, readings, bar, bar_msl)
        summaries.append(s)
        events.append(ev)
        page.append(p)
    if not summaries:
        raise SystemExit("No gauge has enough readings in that period.")
    summary = pd.DataFrame(summaries)
    print_summary(summary)

    out = Path(args.csv_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out / "summary.csv", index=False, float_format="%.3f")
    pd.concat(events, ignore_index=True).to_csv(out / "events.csv", index=False,
                                                float_format="%.3f", date_format="%Y-%m-%d %H:%M")

    built = pd.Timestamp.now(tz=BRISBANE).tz_localize(None) if args.stamp else None
    payload = build_payload(page, bar, bar_msl, readings, args.ref, built)
    write_html(payload, args.template, args.out)
    print(f"\nWrote {args.out}, and summary.csv, events.csv in {out}")
    if args.json:
        payload["summary"] = json.loads(summary.to_json(orient="records"))
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(to_json(payload))
        print("Wrote", args.json)


if __name__ == "__main__":
    main()
