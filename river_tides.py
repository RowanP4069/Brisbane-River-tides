#!/usr/bin/env python3
"""Brisbane River predicted tide explorer.

Pipeline:
  Brisbane Bar 10-min predictions
  -> points along the river centreline (data/centreline.csv), every 500 m by default
  -> lag, ratio and MSL at each point, interpolated along chainage from the
     secondary-port stations (data/stations.csv)
  -> absolute height per point per frame over the window (24 h by default)
  -> output/river_tides.html: web/river_tides_template.html with the data inlined
     (3D map of bars + linked profile; open it from disk in a normal browser).

Tide model (secondary-port method, one lag and one ratio per point):
    height(x, t) = MSL(x) + ratio(x) * (Bar(t - lag(x)) - MSL_Bar)
MSL_Bar is the Brisbane Bar row's msl_m in stations.csv (1.32 m), not a mean of
the Bar file. At the Bar (lag 0, ratio 1) this returns the Bar prediction exactly.

IMPORTANT: heights are on each station's LOCAL LAT datum. They can be shown
per point but must not be differenced between points (see data/README.md).
Excludes freshwater flow, wind, surge and dam releases. Anything derived from
the heights (rising/falling, rate, slope) is a direction proxy, not a current.

Usage:
  python river_tides.py --start 2026-11-08            # uses data/bar_2026_10min.csv
  python river_tides.py --csv OTHER.csv --start ...   # a different Bar file
  python river_tides.py --start ... --json output/check.json   # also dump the data

Sources: see data/README.md.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"


# --- Inputs ----------------------------------------------------------------------

def load_bar(path):
    """Brisbane Bar predictions as a time-indexed Series (metres above LAT).

    Expects the data.qld.gov.au interval CSV: columns _id, Date, Time, Ind, Reading.
    Only Date, Time and Reading are used (_id is a row number; Ind is 9 on every row
    and its meaning is undocumented, see data/README.md).
    Times are AEST (UTC+10, no daylight saving), kept as naive local time.

    Stops with an error if the readings are not a continuous 10-minute series:
    later steps interpolate between samples and would silently bridge a gap.
    """
    # utf-8-sig strips the byte-order mark the file starts with.
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]
    stamp = df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip()
    t = pd.to_datetime(stamp, dayfirst=True)       # dayfirst: Australian DD/MM/YYYY
    # errors="coerce" turns unreadable values into NaN; dropna removes them, and the
    # gap check below then reports the hole they leave.
    s = pd.Series(pd.to_numeric(df["reading"], errors="coerce").values, index=t)
    s = s.dropna().sort_index()

    steps = s.index.to_series().diff().dropna()
    bad = steps[steps != pd.Timedelta(minutes=10)]
    if not bad.empty:
        raise SystemExit(f"{path}: {len(bad)} step(s) are not 10 min, first ending at "
                         f"{bad.index[0]} ({bad.iloc[0]}). Missing or duplicate readings?")
    return s


def load_stations(path):
    """Stations with complete lag, ratio, MSL and chainage, ordered mouth -> upstream.

    The model reads only name, chainage_km, lag_min, ratio and msl_m. The other
    columns (lat, lon, lag_hw_min, lag_lw_min, range_m, note) are reference only:
    editing them does not change the output. lag_min is the mean of the HW and LW lags.
    """
    st = pd.read_csv(path)
    need = ["chainage_km", "lag_min", "ratio", "msl_m"]
    # Mt Crosby Weir is expected here: it is not in the MSQ tables, so its row is blank.
    skipped = st[st[need].isna().any(axis=1)].name.tolist()
    if skipped:
        print("Skipped (incomplete row):", ", ".join(skipped))
    # kind="stable" keeps rows with equal chainage in file order (default sort may not).
    st = st.dropna(subset=need).sort_values("chainage_km", kind="stable").reset_index(drop=True)
    # Boat Passage and the Bar share chainage 0 with identical values. np.interp needs
    # x to increase, so keep one row per chainage: the first in the file, i.e. the Bar.
    return st.drop_duplicates(subset="chainage_km", keep="first").reset_index(drop=True)


def sample_centreline(path, step_km, end_km):
    """Points every step_km along the centreline from 0 to end_km (end included).

    lon/lat are interpolated linearly between centreline vertices by chainage, so each
    point lies exactly on the centreline polyline. How closely that follows the real
    river depends on the centreline itself (vertices typically ~100 m apart).
    """
    cl = pd.read_csv(path)
    # np.arange stops BEFORE end_km, so add end_km as a final point unless the last
    # step already landed on it. 1e-9 absorbs floating-point error in the steps.
    ch = np.arange(0.0, end_km, step_km)
    if end_km - ch[-1] > 1e-9:
        ch = np.append(ch, end_km)          # finish exactly at the last station
    return pd.DataFrame({
        "chainage_km": np.round(ch, 3),
        "lon": np.interp(ch, cl.chainage_km, cl.lon),
        "lat": np.interp(ch, cl.chainage_km, cl.lat),
    })


# --- Model -----------------------------------------------------------------------

def add_corrections(pts, st):
    """Interpolate lag, ratio and MSL from the stations onto each point.

    ASSUMPTION: each varies linearly along the river between stations.
    Points beyond the last station would take its values; sample_centreline stops there.
    """
    for col in ["lag_min", "ratio", "msl_m"]:
        pts[col] = np.interp(pts.chainage_km, st.chainage_km, st[col])
    return pts


def heights(bar, frames, pts, bar_msl):
    """Absolute height (m above local LAT) as a 2-D array [frame, point].

    For each point, look up the Bar lag minutes earlier (linear interpolation between
    10-minute samples), take its departure from the Bar's MSL, scale it by the
    point's ratio, and add the point's own MSL.
    """
    t0 = bar.index[0]
    bar_sec = (bar.index - t0).total_seconds().values
    frame_sec = (frames - t0).total_seconds().values
    anomaly_bar = bar.values - bar_msl

    # want[f, p] = time (s) at which the Bar must be read for frame f at point p.
    # The [:, None] / [None, :] pairs make numpy build the full grid in one step.
    want = frame_sec[:, None] - pts.lag_min.values[None, :] * 60
    a = np.interp(want.ravel(), bar_sec, anomaly_bar, left=np.nan, right=np.nan).reshape(want.shape)
    if np.isnan(a).any():
        raise SystemExit("Bar data does not cover the window plus the largest lag - "
                         "check --start against the CSV.")
    return pts.msl_m.values[None, :] + pts.ratio.values[None, :] * a


# --- Output ----------------------------------------------------------------------

def station_labels(st, centreline_path):
    """Station labels placed ON the centreline at each station's chainage.

    The table's lat/lon are rounded to ~1 arc-minute and can sit off the river, so the
    label goes where the model actually puts the station.
    """
    cl = pd.read_csv(centreline_path)
    # Short form for the profile's x axis: drop anything in brackets.
    short = st.name.str.replace(r"\s*\(.*\)", "", regex=True)
    return [{"name": n, "short": s, "chainage_km": round(float(c), 1),
             "lon": round(float(np.interp(c, cl.chainage_km, cl.lon)), 6),
             "lat": round(float(np.interp(c, cl.chainage_km, cl.lat)), 6)}
            for n, s, c in zip(st.name, short, st.chainage_km)]


def write_html(payload, template_path, out_path):
    """Inline the payload into the page template and write a single self-contained file."""
    html = Path(template_path).read_text(encoding="utf-8")
    marker = "/*__DATA__*/null"
    if html.count(marker) != 1:
        raise SystemExit(f"Template must contain {marker} exactly once: {template_path}")
    # "</" is escaped so a stray "</script>" inside the data can never close the script tag.
    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html.replace(marker, data), encoding="utf-8")


def build_payload(frames, pts, h, start, bar_msl, step_min, stations):
    """Everything the page needs, as plain lists (JSON-ready). Heights rounded to mm."""
    return {
        "meta": {
            "start": start.isoformat(),
            "step_min": step_min,
            "timezone": "AEST (UTC+10)",
            "bar_msl_m": bar_msl,
            "datum": "metres above each station's local LAT (Queensland Port Datum)",
            "model": "MSL(x) + ratio(x) * (Bar(t - lag(x)) - MSL_Bar)",
        },
        "times": [t.strftime("%Y-%m-%dT%H:%M") for t in frames],
        "stations": stations,
        "points": {
            "chainage_km": pts.chainage_km.round(3).tolist(),
            "lon": pts.lon.round(6).tolist(),
            "lat": pts.lat.round(6).tolist(),
            "lag_min": pts.lag_min.round(1).tolist(),
            "ratio": pts.ratio.round(4).tolist(),
            "msl_m": pts.msl_m.round(3).tolist(),
        },
        # heights[frame][point]
        "heights": np.round(h, 3).tolist(),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--csv", default=str(DATA / "bar_2026_10min.csv"),
                    help="Brisbane Bar 10-min prediction CSV (default: the 2026 file in data/)")
    ap.add_argument("--stations", default=str(DATA / "stations.csv"))
    ap.add_argument("--centreline", default=str(DATA / "centreline.csv"))
    ap.add_argument("--start", default=str(pd.Timestamp.now().date()),
                    help="window start, local AEST (default: today 00:00)")
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--step-min", type=int, default=10, help="minutes between frames")
    ap.add_argument("--spacing-km", type=float, default=0.5, help="distance between bars")
    ap.add_argument("--out", default="output/river_tides.html")
    ap.add_argument("--template", default=str(Path(__file__).parent / "web" / "river_tides_template.html"))
    ap.add_argument("--json", help="also write the page data to this JSON file")
    a = ap.parse_args()

    start = pd.Timestamp(a.start)
    frames = pd.date_range(start, start + pd.Timedelta(hours=a.hours), freq=f"{a.step_min}min")

    st = load_stations(a.stations)
    bar_msl = float(st.loc[st.chainage_km == 0, "msl_m"].iloc[0])

    bar = load_bar(a.csv)
    # Keep 1 day either side: the largest lag (~3 h) needs Bar data before the start.
    bar = bar[start - pd.Timedelta(days=1): frames[-1] + pd.Timedelta(days=1)]
    if bar.empty:
        raise SystemExit("No Bar data in the requested window - check --start against the CSV.")

    pts = sample_centreline(a.centreline, a.spacing_km, st.chainage_km.max())
    pts = add_corrections(pts, st)
    h = heights(bar, frames, pts, bar_msl)

    print(f"{len(frames)} frames x {len(pts)} points, "
          f"{frames[0]:%Y-%m-%d %H:%M} to {frames[-1]:%Y-%m-%d %H:%M} AEST; "
          f"heights {h.min():.2f} to {h.max():.2f} m")

    payload = build_payload(frames, pts, h, start, bar_msl, a.step_min,
                            station_labels(st, a.centreline))
    write_html(payload, a.template, a.out)
    print("Wrote", a.out)
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(payload, separators=(",", ":")))
        print("Wrote", a.json)


if __name__ == "__main__":
    main()
