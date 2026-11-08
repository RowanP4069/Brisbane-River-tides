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
  python river_tides.py --start 2026-11-08            # uses every data/bar_YYYY_10min.csv
  python river_tides.py --csv OTHER.csv --start ...   # different Bar file(s)
  python river_tides.py --start ... --json output/check.json   # also dump the data
  python river_tides.py --hours 48 --stamp            # as the hosted page is built

Sources: see data/README.md.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

# Default paths are relative to this script, so it works from any current folder.
HERE = Path(__file__).parent
DATA = HERE / "data"

# All times are Brisbane local (AEST, UTC+10, no daylight saving). "Now" is taken in
# this zone so a machine on another clock (e.g. a UTC build server) gets the same day.
BRISBANE = "Australia/Brisbane"


# --- Inputs ----------------------------------------------------------------------

def load_bars(paths):
    """Brisbane Bar predictions from one or more yearly files, joined in time order.

    The files must join without a gap or overlap (checked after joining), so a
    window can run across New Year.
    """
    return check_steps(pd.concat([load_bar(p) for p in paths]).sort_index(),
                       ", ".join(str(p) for p in paths))


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
    # errors="coerce" turns unreadable values into NaN; dropna removes them, and
    # check_steps() then reports the hole they leave.
    s = pd.Series(pd.to_numeric(df["reading"], errors="coerce").values, index=t)
    return check_steps(s.dropna().sort_index(), path)


def check_steps(s, label):
    """Return s unchanged if every step is exactly 10 minutes; otherwise stop."""
    steps = s.index.to_series().diff().dropna()
    bad = steps[steps != pd.Timedelta(minutes=10)]
    if not bad.empty:
        raise SystemExit(f"{label}: {len(bad)} step(s) are not 10 min, first ending at "
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
    lon, lat = lonlat_at(cl, ch)
    return pd.DataFrame({"chainage_km": np.round(ch, 3), "lon": lon, "lat": lat})


def lonlat_at(cl, chainage_km):
    """lon, lat of the centreline cl at the given chainage(s), by linear interpolation
    between its vertices. Shared by the model points and the station labels so both
    are placed the same way."""
    return (np.interp(chainage_km, cl.chainage_km, cl.lon),
            np.interp(chainage_km, cl.chainage_km, cl.lat))


# --- Model -----------------------------------------------------------------------

def add_corrections(pts, st):
    """Interpolate lag, ratio and MSL from the stations onto each point.

    Adds the columns to pts itself (and returns it, for readability at the call site).
    np.interp needs st.chainage_km strictly increasing; load_stations guarantees it.

    ASSUMPTION: each varies linearly along the river between stations.
    Points beyond the last station would take its values; sample_centreline stops there.
    NOTE: this is where the published lag reversal enters the model. Between
    Indooroopilly (km 37.6, 92.5 min) and Seventeen Mile Rocks (km 44.7, 80 min) the
    interpolated lag falls going upstream (see data/README.md, Known limitations).
    """
    for col in ["lag_min", "ratio", "msl_m"]:
        pts[col] = np.interp(pts.chainage_km, st.chainage_km, st[col])
    return pts


def heights(bar, frames, pts, bar_msl):
    """Absolute height (m above local LAT) as a 2-D array [frame, point].

    For each point, look up the Bar lag minutes earlier (linear interpolation between
    10-minute samples), take its departure from the Bar's MSL, scale it by the
    point's ratio, and add the point's own MSL.

    Linear interpolation between 10-minute samples is accurate to under 1 mm here
    (error <= A*w^2*dt^2/8 with amplitude A ~1 m, M2 w = 0.51 rad/h, dt = 1/6 h),
    which is below the mm rounding of the output.
    """
    # np.interp works on plain numbers, not datetimes, so express every time as
    # seconds since the first Bar reading.
    t0 = bar.index[0]
    bar_sec = (bar.index - t0).total_seconds().values
    frame_sec = (frames - t0).total_seconds().values
    anomaly_bar = bar.values - bar_msl

    # want[f, p] = time (s) at which the Bar must be read for frame f at point p.
    # MINUS the lag: the tide reaches upstream later, so a point now shows what the
    # Bar showed lag minutes ago.
    # The [:, None] / [None, :] pairs make numpy build the full grid in one step.
    want = frame_sec[:, None] - pts.lag_min.values[None, :] * 60
    # left/right=NaN: a time outside the Bar data gives NaN instead of the edge value.
    anomaly = np.interp(want.ravel(), bar_sec, anomaly_bar,
                        left=np.nan, right=np.nan).reshape(want.shape)
    if np.isnan(anomaly).any():
        # Say which end is short. main() has already trimmed bar to the window +/- 1 day,
        # so whichever edge falls inside that margin is the edge of the CSV itself.
        need_from = frames[0] - pd.Timedelta(minutes=float(pts.lag_min.max()))
        why = []
        if need_from < bar.index[0]:
            why.append(f"needs Bar data from {need_from:%Y-%m-%d %H:%M} (upstream points "
                       f"read up to {pts.lag_min.max():.0f} min earlier), but the CSV "
                       f"starts {bar.index[0]:%Y-%m-%d %H:%M}")
        if frames[-1] > bar.index[-1]:
            why.append(f"ends {frames[-1]:%Y-%m-%d %H:%M} (the last frame is included), "
                       f"but the CSV ends {bar.index[-1]:%Y-%m-%d %H:%M}")
        raise SystemExit("Window " + "; and ".join(why or ["is not covered by the Bar data"])
                         + ". Adjust --start/--hours, or add that year's CSV "
                           "(fetch_bar.py --year YYYY).")
    return pts.msl_m.values[None, :] + pts.ratio.values[None, :] * anomaly


# --- Output ----------------------------------------------------------------------

def station_labels(st, centreline_path):
    """Station labels placed ON the centreline at each station's chainage.

    The table's lat/lon are rounded to ~1 arc-minute and can sit off the river, so the
    label goes where the model actually puts the station.

    st is the output of load_stations, so Mt Crosby Weir (no data) and Boat Passage
    (merged into the Bar at km 0) get no label.
    """
    cl = pd.read_csv(centreline_path)
    lon, lat = lonlat_at(cl, st.chainage_km)
    # Short form for the profile's x axis: drop anything in brackets.
    short = st.name.str.replace(r"\s*\(.*\)", "", regex=True)
    return [{"name": n, "short": s, "chainage_km": round(float(c), 1),
             "lon": round(float(x), 6), "lat": round(float(y), 6)}
            for n, s, c, x, y in zip(st.name, short, st.chainage_km, lon, lat)]


def build_payload(frames, pts, h, bar_msl, step_min, stations, built=None):
    """Everything the page needs, as plain lists (JSON-ready). Becomes DATA in the page.

    built: when the page was made, as a naive AEST Timestamp, or None to leave the
    stamp out (the default, so repeat runs give byte-identical output).

    Rounding: chainage to 1 m, lon/lat to 6 decimals (~0.1 m), lag to 0.1 min,
    ratio to 4 decimals and heights to 1 mm. That is finer than the model's accuracy
    and keeps the page small (the heights grid is most of it).
    """
    meta = {
        "start": frames[0].isoformat(),
        "step_min": step_min,
        "timezone": "AEST (UTC+10)",
        "bar_msl_m": bar_msl,
        "datum": "metres above each station's local LAT "
                 "(Queensland Port Datum, assumed; see data/README.md)",
        "model": "MSL(x) + ratio(x) * (Bar(t - lag(x)) - MSL_Bar)",
    }
    if built is not None:
        meta["built"] = built.strftime("%Y-%m-%dT%H:%M")    # same format as times
    return {
        # The page reads meta.step_min and, if present, meta.built. The other fields
        # describe the data for anyone reading the --json file on its own.
        "meta": meta,
        # Naive AEST, no seconds. fmtTime() in the template appends ":00" to parse
        # these, so change both together.
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


def write_html(payload, template_path, out_path):
    """Inline the payload into the page template and write a single self-contained file."""
    html = Path(template_path).read_text(encoding="utf-8")
    # The template has `const DATA = /*__DATA__*/null;`. The trailing null keeps the
    # unfilled template valid JavaScript, so opening it directly fails cleanly
    # (DATA is null) rather than with a syntax error.
    marker = "/*__DATA__*/null"
    if html.count(marker) != 1:
        raise SystemExit(f"Template must contain {marker} exactly once: {template_path}")
    # "</" is escaped so a stray "</script>" inside the data can never close the script tag.
    data = to_json(payload).replace("</", "<\\/")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html.replace(marker, data), encoding="utf-8")


def to_json(payload):
    """Compact JSON (no spaces) for the page and the --json file."""
    return json.dumps(payload, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--csv", nargs="+",
                    default=sorted(str(p) for p in DATA.glob("bar_*_10min.csv")),
                    help="Brisbane Bar 10-min prediction CSV file(s), joined in time order "
                         "(default: every data/bar_YYYY_10min.csv, so windows can cross New Year)")
    ap.add_argument("--stations", default=str(DATA / "stations.csv"),
                    help="secondary-port stations: chainage, lag, ratio, MSL (default: data/)")
    ap.add_argument("--centreline", default=str(DATA / "centreline.csv"),
                    help="river centreline from build_centreline.py (default: data/)")
    ap.add_argument("--start", default=str(pd.Timestamp.now(tz=BRISBANE).date()),
                    help="window start, local AEST, e.g. 2026-11-08 or 2026-11-08T06:00 "
                         "(default: today 00:00 in Brisbane)")
    ap.add_argument("--hours", type=float, default=24,
                    help="window length in hours; the end frame is included (default: 24)")
    ap.add_argument("--step-min", type=int, default=10,
                    help="minutes between frames (default: 10). If it does not divide the "
                         "window evenly, the window ends on the last whole step")
    ap.add_argument("--spacing-km", type=float, default=0.5,
                    help="distance between bars along the river, km (default: 0.5)")
    ap.add_argument("--out", default=str(HERE / "output" / "river_tides.html"),
                    help="page to write (default: output/river_tides.html)")
    ap.add_argument("--template", default=str(HERE / "web" / "river_tides_template.html"),
                    help="page template with the /*__DATA__*/null marker (default: web/)")
    ap.add_argument("--json", help="also write the page data to this JSON file")
    ap.add_argument("--stamp", action="store_true",
                    help="show on the page when it was built (AEST). Off by default so "
                         "repeat runs give identical files; the hosted page uses it")
    args = ap.parse_args()

    if args.step_min < 1:
        ap.error("--step-min must be at least 1")
    if args.spacing_km <= 0:
        ap.error("--spacing-km must be more than 0")
    start = pd.Timestamp(args.start)
    frames = pd.date_range(start, start + pd.Timedelta(hours=args.hours),
                           freq=f"{args.step_min}min")
    # The page works out rates from neighbouring frames, so it needs at least two.
    if len(frames) < 2:
        ap.error(f"--hours {args.hours:g} with --step-min {args.step_min} gives "
                 f"{len(frames)} frame(s); need at least 2")

    st = load_stations(args.stations)
    # MSL_Bar in the model: the Bar's row (chainage 0) of stations.csv, 1.32 m.
    bar_msl = float(st.loc[st.chainage_km == 0, "msl_m"].iloc[0])

    full = load_bars(args.csv)
    # Trim to the window with a 1-day margin each side, which is ample for the largest
    # lag (160 min, Kholo). heights() checks the coverage exactly.
    bar = full[start - pd.Timedelta(days=1): frames[-1] + pd.Timedelta(days=1)]
    if bar.empty:
        raise SystemExit(f"No Bar data near the window: the CSV covers "
                         f"{full.index[0]:%Y-%m-%d %H:%M} to {full.index[-1]:%Y-%m-%d %H:%M}. "
                         "Check --start, or add that year's CSV (fetch_bar.py --year YYYY).")

    pts = sample_centreline(args.centreline, args.spacing_km, st.chainage_km.max())
    pts = add_corrections(pts, st)
    h = heights(bar, frames, pts, bar_msl)

    print(f"{len(frames)} frames x {len(pts)} points, "
          f"{frames[0]:%Y-%m-%d %H:%M} to {frames[-1]:%Y-%m-%d %H:%M} AEST; "
          f"heights {h.min():.2f} to {h.max():.2f} m")

    built = pd.Timestamp.now(tz=BRISBANE).tz_localize(None) if args.stamp else None
    payload = build_payload(frames, pts, h, bar_msl, args.step_min,
                            station_labels(st, args.centreline), built)
    write_html(payload, args.template, args.out)
    print("Wrote", args.out)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(to_json(payload))
        print("Wrote", args.json)


if __name__ == "__main__":
    main()
