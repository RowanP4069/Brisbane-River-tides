#!/usr/bin/env python3
"""Brisbane River predicted tide explorer.

Pipeline:
  Brisbane Bar 10-min predictions
  -> points along the river centreline (data/centreline.csv), every 500 m by default
  -> lag, ratio and MSL at each point, interpolated along chainage from the
     secondary-port stations (data/stations.csv)
  -> absolute height per point per frame over the window (48 h by default), for the
     --json reference
  -> output/index.html: web/predictions_template.html with the data inlined
     (3D map of bars + linked profile; open it from disk in a normal browser). The
     page gets the whole Bar series and each point's lag, ratio and MSL, and works
     out the heights itself for whichever day the viewer picks (check_parity.py
     checks it matches the heights here).

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
  python river_tides.py --stamp                       # as the hosted page is built

Sources: see data/README.md.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rivers

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


def load_stations(path, river=rivers.DEFAULT):
    """Stations with complete lag, ratio, MSL and chainage, ordered mouth -> upstream.

    The model reads only name, chainage_km, lag_min, ratio and msl_m. The other
    columns (lat, lon, lag_hw_min, lag_lw_min, range_m, note) are reference only:
    editing them does not change the output. lag_min is the mean of the HW and LW lags.
    Only the given river's rows are used (column river; blank = brisbane).
    """
    st = rivers.only(pd.read_csv(path), river)
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


def ramp_places(path, end_km):
    """Boat ramps from data/ramps.csv inside the predicted reach (km 0 to end_km), for
    the page's Place list. Location references only: name and chainage, as on the
    report page."""
    r = rivers.only(pd.read_csv(path))
    r = r[(r.km >= 0) & (r.km <= end_km)].sort_values("km")
    return [{"name": n, "chainage_km": round(float(k), 2)} for n, k in zip(r.name, r.km)]


def build_payload(frames, pts, h, bar_msl, step_min, stations, full_bar, hours,
                  start_is_default, built=None, ramps=()):
    """Everything the page needs, as plain lists (JSON-ready). Becomes DATA in the page.

    The page computes heights itself for whichever day the viewer picks, from "model":
    the whole Bar series (full_bar, in mm) and each point's lag, ratio and MSL at full
    precision, so it matches heights() here (check_parity.py tests that). Python stays
    the source of truth for everything about places; the page only applies the formula.

    "times" and "heights" are this run's window (--start, --hours) worked out by
    heights(). They go into the --json file, as the reference check_parity.py compares
    the page against, but not into the page (write_html leaves them out).

    hours, start_is_default: the page opens on this window length, and on the --start
    day if one was given, otherwise on the viewer's today (Brisbane).
    built: when the page was made, as a naive AEST Timestamp, or None to leave the
    stamp out (the default, so repeat runs give byte-identical output).
    ramps: boat ramps for the page's Place list (see ramp_places).

    Rounding in "points" (for display): chainage to 1 m, lon/lat to 6 decimals (~0.1 m),
    lag to 0.1 min, ratio to 4 decimals; "heights" to 1 mm. Finer than the model's
    accuracy. "model" is not rounded; the Bar series is whole mm, as published.
    """
    meta = {
        "start": frames[0].isoformat(),
        "start_is_default": start_is_default,
        "hours": hours,
        "step_min": step_min,
        "timezone": "AEST (UTC+10)",
        "bar_msl_m": bar_msl,
        "datum": "metres above each station's local LAT "
                 "(Queensland Port Datum, assumed; see data/README.md)",
        "model": "MSL(x) + ratio(x) * (Bar(t - lag(x)) - MSL_Bar)",
    }
    if built is not None:
        meta["built"] = built.strftime("%Y-%m-%dT%H:%M")    # same format as times
    bar_mm = np.round(full_bar.values * 1000).astype(int)
    # The CSVs give metres to 3 decimals, so whole mm lose nothing; check, in case a
    # future file has more decimals.
    if np.abs(bar_mm / 1000 - full_bar.values).max() > 1e-9:
        raise SystemExit("Bar readings are not whole millimetres; the page's mm encoding "
                         "would round them")
    return {
        # The page reads meta.step_min, start, start_is_default, hours and (if present)
        # built. The other fields describe the data for anyone reading the --json file.
        "meta": meta,
        "model": {
            "bar_start": full_bar.index[0].strftime("%Y-%m-%dT%H:%M"),
            "bar_step_min": 10,                         # load_bars() guarantees it
            "bar_mm": bar_mm.tolist(),
            "bar_msl_m": bar_msl,
            # Not rounded (unlike "points"), so the page reproduces heights() exactly.
            "lag_min": pts.lag_min.tolist(),
            "ratio": pts.ratio.tolist(),
            "msl_m": pts.msl_m.tolist(),
        },
        # Naive AEST, no seconds. fmtTime() in the template appends ":00" to parse
        # these, so change both together.
        "times": [t.strftime("%Y-%m-%dT%H:%M") for t in frames],
        "stations": stations,
        "ramps": list(ramps),
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


# --- Sandbox: the Guesswork page (--sandbox) -------------------------------------------
# Above Kholo Creek the project makes no predictions (docs/hypotheses.md). The sandbox
# page carries on to the old weir ruin with GUESSES, each named and dated in
# data/guesses.csv, so they can be looked at and argued with. Nothing here changes the
# model below Kholo, and the normal page is built without any of it.

SANDBOX_END_FEATURE = "weir-ruin"             # the sandbox reach ends at the old weir ruin
# Features labelled on the sandbox map and profile axis (feature_id -> short name), as
# the MSQ stations are below Kholo.
SANDBOX_LABELS = {"bridge-colleges-crossing": "Colleges Crossing", "weir-ruin": "Weir ruin"}
# The sandbox page's <title>, and the tag that keeps it out of search engines.
SANDBOX_TITLE = "Guesswork: Kholo Creek to the weir ruin"
NOINDEX = '<meta name="robots" content="noindex">'


def load_guesses(path):
    """data/guesses.csv, one row per guess, indexed by id. not_a_test_on becomes a list
    of dates (a guess tuned on a day's data can't count as a test on that day)."""
    g = pd.read_csv(path, dtype={"not_a_test_on": str, "feature_id": str})
    g["not_a_test_on"] = g.not_a_test_on.fillna("").map(lambda s: [d for d in s.split(";") if d])
    g["feature_id"] = g.feature_id.fillna("")
    for need in ["G-lag", "G-ratio", "G-datum"]:
        if need not in set(g.id):
            raise SystemExit(f"{path}: no row for {need}")
    if g.id.duplicated().any():
        raise SystemExit(f"{path}: duplicate ids {sorted(set(g.id[g.id.duplicated()]))}")
    return g.set_index("id", drop=False)


def apply_guess_lag_ratio(pts, guesses, from_km):
    """Points above from_km (Kholo Creek) take G-lag and G-ratio. Their MSL stays at
    Kholo Creek's (add_corrections holds the last station's value), so their heights
    are on Kholo Creek's LAT."""
    above = pts.chainage_km > from_km + 1e-9
    pts.loc[above, "lag_min"] = float(guesses.loc["G-lag", "value"])
    pts.loc[above, "ratio"] = float(guesses.loc["G-ratio", "value"])
    return pts


def sandbox_block(guesses, features, obs, from_km, to_km):
    """What the template needs to draw the guess reach (DATA.sandbox).

    floors: gravel-run crests (G-floor-*). Above a crest's km the guess height is the
      larger of the tide and the crest; the page applies this after the model.
    places: river features in the guess reach, for the Place list.
    observations: the project's field observations above from_km, as dark markers.
    """
    fe = features.set_index("feature_id", drop=False)
    rows = []
    for g in guesses.itertuples():
        km = g.km if pd.notna(g.km) else None
        rows.append({"id": g.id, "dated": g.dated, "value": float(g.value),
                     "unit": g.unit if pd.notna(g.unit) else "",
                     "feature": fe.loc[g.feature_id, "name"] if g.feature_id else "",
                     "km": km, "not_a_test_on": g.not_a_test_on, "basis": g.basis})
    floors = [{"id": r["id"], "km": r["km"], "crest_m": r["value"], "name": r["feature"]}
              for r in rows if r["id"].startswith("G-floor")]
    if any(f["km"] is None for f in floors):
        raise SystemExit("guesses.csv: every G-floor row needs a km")
    places = []
    for f in features.itertuples():
        if from_km < f.km <= to_km and f.kind in ("gravel run", "structure", "gauge"):
            pl = {"name": f.name, "chainage_km": round(float(f.km), 2)}
            if f.feature_id in SANDBOX_LABELS:       # also labelled on the map and profile
                pl.update(short=SANDBOX_LABELS[f.feature_id],
                          lon=round(float(f.lon), 6), lat=round(float(f.lat), 6))
            places.append(pl)
    observations = []
    for o in obs.itertuples():
        k_from, k_to = float(o.km_from), float(o.km_to)
        if k_to <= from_km:
            continue
        f = fe.loc[o.feature_id] if o.feature_id in fe.index else None
        # A height only for the state of a level mark (covered or not): that says where
        # the water was. A high-water time read at a gauge plate is not a height.
        ahd = (f.height_m_ahd if o.quantity == "mark_state" and f is not None
               and pd.notna(f.height_m_ahd) else None)
        observations.append({
            "id": o.obs_id, "from": o.time_from_aest.replace(" ", "T"),
            "to": o.time_to_aest.replace(" ", "T"), "km": round((k_from + k_to) / 2, 2),
            "quantity": o.quantity, "value": o.value, "confidence": o.confidence,
            "feature": f["name"] if f is not None else "",
            "height_m_ahd": float(ahd) if ahd is not None else None,
        })
    return {"from_km": from_km, "to_km": to_km,
            "datum_ahd": float(guesses.loc["G-datum", "value"]),
            "guesses": rows, "floors": sorted(floors, key=lambda f: f["km"]),
            "places": sorted(places, key=lambda p: p["chainage_km"]),
            "observations": sorted(observations, key=lambda o: (o["from"], o["km"]))}


HEAD_CHART_KM = 75.0          # the tidal-head chart shows reports from here upstream


def head_chart(bar, bar_msl, st, features, obs, to_km):
    """Data for the Guesswork page's tidal-head chart: what was seen above about km 75,
    against the predicted Kholo Creek level at the time (MSQ's figures; no guesses).

    reports: accepted flow reports (the reports branch, as on the results page).
    observations: our field observations, with the Kholo level range over each one as
      recorded in observations.csv (kholo_min_m, kholo_max_m).
    lines: features drawn across the chart (gravel runs, the ruin), and Kholo Creek.
    """
    from build_results import all_reports              # the results page's loader
    kholo = st.iloc[[-1]][["lag_min", "ratio", "msl_m"]].reset_index(drop=True)
    reports = [r for r in all_reports() if float(r["km"]) >= HEAD_CHART_KM]
    times = pd.DatetimeIndex([pd.Timestamp(r["time_aest"]) for r in reports])
    lev = heights(bar, times, kholo, bar_msl)[:, 0] if len(times) else []
    soon = heights(bar, times + pd.Timedelta(minutes=10), kholo, bar_msl)[:, 0] if len(times) else []
    out_reports = [{"time": r["time_aest"], "km": float(r["km"]), "dir": r["dir"],
                    "kholo_m": round(float(h), 3), "kholo_rising": bool(h2 > h)}
                   for r, h, h2 in zip(reports, lev, soon)]
    out_obs = []
    for o in obs.itertuples():
        if float(o.km_to) < HEAD_CHART_KM or not o.kholo_min_m:
            continue
        out_obs.append({"id": o.obs_id, "from": o.time_from_aest, "to": o.time_to_aest,
                        "km": round((float(o.km_from) + float(o.km_to)) / 2, 2),
                        "quantity": o.quantity, "value": o.value,
                        "kholo_min_m": float(o.kholo_min_m), "kholo_max_m": float(o.kholo_max_m)})
    lines = [{"name": f.name, "km": float(f.km), "kind": f.kind}
             for f in features.itertuples()
             if f.kind == "gravel run" or f.feature_id == SANDBOX_END_FEATURE]
    lines.append({"name": "Kholo Creek (MSQ figures end)", "km": float(st.chainage_km.max()),
                  "kind": "limit"})
    return {"from_km": HEAD_CHART_KM, "to_km": to_km, "reports": out_reports,
            "observations": out_obs, "lines": sorted(lines, key=lambda l: l["km"])}


def write_html(payload, template_path, out_path):
    """Inline the payload into the page template and write a single self-contained file.

    "times" and "heights" are left out: the page computes its own windows from "model".
    """
    html = Path(template_path).read_text(encoding="utf-8")
    payload = {k: v for k, v in payload.items() if k not in ("times", "heights")}
    # The template has `const DATA = /*__DATA__*/null;`. The trailing null keeps the
    # unfilled template valid JavaScript, so opening it directly fails cleanly
    # (DATA is null) rather than with a syntax error.
    marker = "/*__DATA__*/null"
    if html.count(marker) != 1:
        raise SystemExit(f"Template must contain {marker} exactly once: {template_path}")
    # "</" is escaped so a stray "</script>" inside the data can never close the script tag.
    data = to_json(payload).replace("</", "<\\/")
    if "sandbox" in payload:
        # Done here, not by the page's script, so a search engine that doesn't run
        # JavaScript still sees them.
        for old, new in [("<title>Brisbane River Tides</title>", f"<title>{SANDBOX_TITLE}</title>"),
                         ('<meta charset="utf-8">', '<meta charset="utf-8">\n' + NOINDEX)]:
            if html.count(old) != 1:
                raise SystemExit(f"Template must contain {old} exactly once: {template_path}")
            html = html.replace(old, new)
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
    ap.add_argument("--start",
                    help="window start, local AEST, e.g. 2026-11-08 or 2026-11-08T06:00. "
                         "The page opens on this day (and keeps the time of day when "
                         "another day is picked). Default: today 00:00 in Brisbane, and "
                         "the page opens on the viewer's today")
    ap.add_argument("--hours", type=float, default=48,
                    help="window length in hours; the end frame is included (default: 48). "
                         "The page offers 24 and 48, plus this if different")
    ap.add_argument("--step-min", type=int, default=10,
                    help="minutes between frames (default: 10). If it does not divide the "
                         "window evenly, the window ends on the last whole step")
    ap.add_argument("--spacing-km", type=float, default=0.5,
                    help="distance between bars along the river, km (default: 0.5)")
    ap.add_argument("--ramps", default=str(DATA / "ramps.csv"),
                    help="boat ramps for the page's Place list (default: data/)")
    ap.add_argument("--out",
                    help="page to write (default: output/index.html, as on the website; "
                         "output/guesswork.html with --sandbox)")
    ap.add_argument("--sandbox", action="store_true",
                    help="build the Guesswork page instead: the same model to Kholo Creek, "
                         "then GUESSES from data/guesses.csv up to the old weir ruin")
    ap.add_argument("--template", default=str(HERE / "web" / "predictions_template.html"),
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
    start_is_default = args.start is None
    start = pd.Timestamp(args.start or pd.Timestamp.now(tz=BRISBANE).date())
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

    kholo_km = float(st.chainage_km.max())
    end_km = kholo_km
    if args.sandbox:
        features = rivers.only(pd.read_csv(DATA / "features.csv"))
        end_km = float(features.loc[features.feature_id == SANDBOX_END_FEATURE, "km"].iloc[0])
        guesses = load_guesses(DATA / "guesses.csv")
    if args.out is None:
        args.out = str(HERE / "output" / ("guesswork.html" if args.sandbox else "index.html"))

    pts = sample_centreline(args.centreline, args.spacing_km, end_km)
    pts = add_corrections(pts, st)
    if args.sandbox:
        pts = apply_guess_lag_ratio(pts, guesses, kholo_km)
    h = heights(bar, frames, pts, bar_msl)

    print(f"{len(frames)} frames x {len(pts)} points, "
          f"{frames[0]:%Y-%m-%d %H:%M} to {frames[-1]:%Y-%m-%d %H:%M} AEST; "
          f"heights {h.min():.2f} to {h.max():.2f} m")

    built = pd.Timestamp.now(tz=BRISBANE).tz_localize(None) if args.stamp else None
    payload = build_payload(frames, pts, h, bar_msl, args.step_min,
                            station_labels(st, args.centreline), full, args.hours,
                            start_is_default, built,
                            ramp_places(args.ramps, pts.chainage_km.max()))
    if args.sandbox:
        obs = rivers.only(pd.read_csv(DATA / "observations.csv", dtype=str).fillna(""))
        payload["sandbox"] = sandbox_block(guesses, features, obs, kholo_km, end_km)
        payload["sandbox"]["head"] = head_chart(full, bar_msl, st, features, obs, end_km)
    write_html(payload, args.template, args.out)
    print("Wrote", args.out)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(to_json(payload))
        print("Wrote", args.json)


if __name__ == "__main__":
    main()
