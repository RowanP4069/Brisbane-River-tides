#!/usr/bin/env python3
"""Brisbane River predicted tide explorer (approach A: levels + rising/falling).

Pipeline: Brisbane Bar 10-min predictions -> shift/scale per station using
secondary-port lag & ratio (stations.csv), interpolated linearly along the river
-> rate of level change (m/h) -> interactive Plotly HTML + CSV table.

IMPORTANT: rate of rise/fall is a DIRECTION indicator (rising ~ flood, falling ~ ebb),
NOT a velocity. Excludes freshwater flow, wind, surge, dam releases.

Usage:
  pip install pandas numpy plotly
  python river_tides.py --demo           # synthetic data, tests the pipeline
  python river_tides.py --csv data/bar_2026_10min.csv --start 2026-10-10 --days 7

Sources:
    - https://www.data.qld.gov.au/dataset/brisbane-bar-tide-gauge-predicted-interval-data/resource/11f33b0e-953f-46f4-84a9-1aa0a779a5e7
    - https://www.bom.gov.au/oceanography/projects/ntc/qld_tide_tables.shtml
    - https://www.msq.qld.gov.au/tides/open-data
    - https://www.msq.qld.gov.au/tides/tidal-planes
"""
# The text in triple quotes above is the module "docstring". Python ignores it when
# running, but help() and IDEs (hover in PyCharm) show it as documentation.

# --- Imports -------------------------------------------------------------------
# argparse : standard library, turns command-line flags (--csv, --days ...) into variables.
# Path     : standard library, a tidy way to build file paths that works on any OS.
# numpy    : fast maths on whole arrays at once (no Python loops needed).
# pandas   : tables (DataFrame) and labelled columns (Series), great for CSVs and dates.
# plotly   : interactive charts saved as an HTML page you open in a browser.
# The "as np" / "as pd" / "as go" parts are just short nicknames - a universal convention.
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def load_bar(path):
    """Expects columns Date, Time, (Ind), Reading as in the data.qld.gov.au interval CSV.
    Times are AEST (UTC+10, no DST), kept as naive local time."""
    # Read the whole CSV into a DataFrame (think: a spreadsheet in memory).
    df = pd.read_csv(path)

    # Normalise the column names: strip stray spaces and lowercase them, so "Date ",
    # "DATE" and "date" all become "date". (The real file also starts with an invisible
    # byte-order mark on "_id", which is why it's safer not to rely on exact names.)
    # This is a "list comprehension": [do_something(c) for c in things] builds a new list.
    df.columns = [c.strip().lower() for c in df.columns]

    # Glue the Date and Time text columns together ("01/01/2026" + " " + "00:10")
    # and convert to real datetime values. dayfirst=True because Australian dates
    # are DD/MM/YYYY - without it, 02/01 could be read as 1 February.
    t = pd.to_datetime(df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip(),
                       dayfirst=True)

    # Build a Series: one column of numbers (the tide height in metres) whose
    # "index" (row labels) is the datetimes. A time-indexed Series lets us later
    # slice by date, e.g. bar["2026-10-05":"2026-10-12"].
    # errors="coerce" turns any unreadable value into NaN ("not a number") instead of crashing.
    s = pd.Series(pd.to_numeric(df["reading"], errors="coerce").values, index=t)

    # Drop the NaN rows and make sure times are in order (needed for interpolation later).
    return s.dropna().sort_index()


def demo_bar(start, days):
    """Crude synthetic tide (M2+S2+K1+O1). For pipeline testing only."""
    # Make a list of timestamps every 10 minutes. 144 = 24 h * 6 per hour.
    # We start 2 days early and add 4 extra days so there's spare data either side
    # of the window you asked for (main() trims it back down to +/- 1 day).
    idx = pd.date_range(pd.Timestamp(start) - pd.Timedelta(days=2),
                        periods=(days + 4) * 144, freq="10min")

    # Convert each timestamp to "hours since the first one" as plain numbers,
    # because the cosine maths below needs numbers, not dates.
    h = (idx - idx[0]).total_seconds().values / 3600

    # A real tide is roughly a sum of cosine waves ("tidal constituents"), each with its
    # own period. Here: mean level 1.7 m, plus
    #   M2 (moon, 12.42 h), S2 (sun, 12.00 h)   -> the twice-daily tides
    #   K1 (23.93 h), O1 (25.82 h)              -> the once-daily wobble
    # Because h is a numpy array, this one line computes every time step at once.
    # The trailing backslash "\" just continues the expression on the next line.
    y = 1.7 + 0.65*np.cos(2*np.pi*h/12.42) + 0.2*np.cos(2*np.pi*h/12.0 + 1) \
        + 0.15*np.cos(2*np.pi*h/23.93) + 0.1*np.cos(2*np.pi*h/25.82)
    return pd.Series(y, index=idx)


def shifted(vals, tsec, lag_min, ratio):
    """Level anomaly at a point lagged by lag_min behind the Bar, scaled by ratio."""
    # This is the core idea of the whole program (the "secondary port" method):
    # the tide upriver looks like the tide at the Bar, but
    #   - LATER  (it takes time for the wave to travel upstream) -> lag_min
    #   - BIGGER (the river narrows and amplifies it)             -> ratio
    #
    # Step by step:
    #   vals - vals.mean()      : turn heights into an "anomaly" = height above/below
    #                             average. We scale the swing, not the absolute height.
    #   tsec - lag_min * 60     : for each moment t at the station, look up what the
    #                             Bar was doing lag seconds EARLIER.
    #   np.interp(want, have_x, have_y) : linear interpolation - estimates values at
    #                             times between the 10-minute samples (lags like 13.5 min
    #                             don't land exactly on a sample).
    #   left/right=np.nan       : if we'd need Bar data from before the file starts,
    #                             return NaN rather than invent a value.
    #   ratio * ...             : stretch the swing by the station's range ratio.
    return ratio * np.interp(tsec - lag_min * 60, tsec, vals - vals.mean(),
                             left=np.nan, right=np.nan)


def main():
    # --- 1. Read the command-line options ---------------------------------------
    # Each add_argument defines one flag. "--csv-out" becomes a.csv_out (dashes -> underscores).
    # Running with --help prints all of these automatically.
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")                                   # path to the Bar tide CSV
    # Path(__file__).parent = the folder this script lives in, so the default works
    # no matter which folder you run the script from.
    ap.add_argument("--stations", default=str(Path(__file__).parent / "data" / "stations.csv"))
    ap.add_argument("--start", default=str(pd.Timestamp.now().date()))  # default: today
    ap.add_argument("--days", type=int, default=7)             # type=int converts "7" text -> 7
    ap.add_argument("--out", default="river_tide.html")
    ap.add_argument("--demo", action="store_true")             # a switch: present = True, absent = False
    ap.add_argument("--csv-out", default="river_tide.csv",
                    help="per-station level anomaly (m) and rate (m/h) table")
    a = ap.parse_args()                                        # a.csv, a.days, a.demo, ...
    if not (a.csv or a.demo):
        ap.error("give --csv PATH or --demo")                  # prints usage and exits

    # --- 2. Load the Brisbane Bar tide and trim it to the time window -------------
    # Timedelta is a length of time; adding it to a Timestamp gives a new Timestamp.
    start = pd.Timestamp(a.start)
    end = start + pd.Timedelta(days=a.days)

    # "X if condition else Y" is Python's one-line if/else.
    bar = demo_bar(start, a.days) if a.demo else load_bar(a.csv)

    # pad 1 day each side so lagged points have data at the window edges
    # (Kholo Creek lags ~160 min, so at 00:00 on day 1 it needs Bar data from the
    # previous evening.) Slicing a time-indexed Series with [from:to] keeps that date range.
    bar = bar[start - pd.Timedelta(days=1): end + pd.Timedelta(days=1)]
    if bar.empty:
        raise SystemExit("No data in the requested window - check --start against the CSV.")

    # --- 3. Load the stations table (lag + ratio for each place along the river) ---
    st = pd.read_csv(a.stations)
    # Boolean filtering: st.lag_min.isna() is a True/False column; "|" means OR.
    # st[mask] keeps only rows where the mask is True. Here: rows we can't use.
    skipped = st[st.lag_min.isna() | st.ratio.isna()].name.tolist()
    # Keep only complete rows, ordered from the river mouth upstream.
    st = st.dropna(subset=["chainage_km", "lag_min", "ratio"]).sort_values("chainage_km")
    if skipped:
        print("Skipped (missing lag/ratio):", ", ".join(skipped))

    # --- 4. Compute the tide all along the river ---------------------------------
    # Time as plain numbers: seconds since the first sample (0, 600, 1200, ...).
    # np.interp and np.gradient work with numbers, not datetimes.
    tsec = (bar.index - bar.index[0]).total_seconds().values

    # x = positions along the river every 1 km (0, 1, 2, ... 56, 56.6).
    # 1 km grid, ending exactly at the last station (no extrapolation past it)
    x = np.append(np.arange(st.chainage_km.min(), st.chainage_km.max(), 1.0), st.chainage_km.max())

    # We only know lag/ratio AT the stations. For every km in between, estimate them by
    # drawing straight lines between neighbouring stations (linear interpolation again,
    # this time along distance instead of time).
    lag = np.interp(x, st.chainage_km, st.lag_min)      # ASSUMPTION: linear along river
    rat = np.interp(x, st.chainage_km, st.ratio)

    # For each km: compute its lagged+scaled tide curve. zip(lag, rat) pairs them up:
    # (lag at km 0, ratio at km 0), (lag at km 1, ratio at km 1), ...
    # np.vstack stacks the curves into a 2-D grid: h[row = km, column = time].
    h = np.vstack([shifted(bar.values, tsec, l, r) for l, r in zip(lag, rat)])

    # Rate of change = slope of each curve: (change in level) / (change in time).
    # Passing tsec/3600 (hours) as the spacing gives metres per hour.
    # axis=1 means "differentiate along the time direction" (columns), not along the river.
    rate = np.gradient(h, tsec / 3600, axis=1)          # m/h, + rising, - falling

    # --- 5. Build the interactive chart ------------------------------------------
    # win is a True/False array marking samples inside the requested window
    # (dropping the 1-day padding). "&" means AND for arrays.
    win = (bar.index >= start) & (bar.index <= end)

    # Two stacked plots sharing one time axis: heatmap on top (60%), lines below (40%).
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.6, 0.4],
                        vertical_spacing=0.06,
                        subplot_titles=("Rate of level change along river (red = rising/flood-ish, "
                                        "blue = falling/ebb-ish)", "Predicted level anomaly at stations"))

    # Heatmap: x = time, y = km along river, colour = rate.
    # rate[:, win] means "all rows (every km), only the columns inside the window".
    # zmid=0 makes zero white; RdBu_r = red for positive (rising), blue for negative.
    # The trailing "1, 1" puts this trace in row 1, column 1.
    fig.add_trace(go.Heatmap(x=bar.index[win], y=x, z=rate[:, win], zmid=0, zmin=-0.8, zmax=0.8,
                             colorscale="RdBu_r", colorbar=dict(title="m/h", len=0.55, y=0.8),
                             hovertemplate="%{x}<br>km %{y}<br>%{z:.2f} m/h<extra></extra>"), 1, 1)

    # --- 6. One line per station on the bottom plot, and collect the CSV columns ---
    # table is a dict: {column name: column values}. pandas turns it into a table later.
    table = {}
    # itertuples() loops over table rows; r.name, r.lag_min etc. are that row's values.
    for r in st.itertuples():
        y = shifted(bar.values, tsec, r.lag_min, r.ratio)
        fig.add_trace(go.Scatter(x=bar.index[win], y=y[win], name=r.name, mode="lines"), 2, 1)
        # f"..." strings insert variables inside {}, e.g. "Pinkenba level (m)".
        table[f"{r.name} level (m)"] = y[win]
        # Same slope calculation as above, but for just this one station's curve.
        table[f"{r.name} rate (m/h)"] = np.gradient(y, tsec / 3600)[win]

    # Axis labels, a draggable range slider under the bottom plot, overall size/title.
    # hovermode="x unified" shows every line's value at the hovered time in one tooltip.
    fig.update_yaxes(title_text="Chainage from mouth (km)", row=1, col=1)
    fig.update_yaxes(title_text="Level anomaly (m)", row=2, col=1)
    fig.update_xaxes(title_text="Local time (AEST, UTC+10)", rangeslider_visible=True, row=2, col=1)
    fig.update_layout(height=800, title="Brisbane River - predicted tide, mouth to tidal limit "
                      "(direction indicator only, not velocity)", hovermode="x unified")

    # --- 7. Save the outputs -----------------------------------------------------
    # include_plotlyjs="cdn" keeps the HTML small by loading plotly from the internet.
    fig.write_html(a.out, include_plotlyjs="cdn")
    print("Wrote", a.out)
    # Turn the dict into a DataFrame with time as the first column, round to mm, save.
    pd.DataFrame(table, index=pd.Index(bar.index[win], name="time_aest")) \
        .round(3).to_csv(a.csv_out)
    print("Wrote", a.csv_out)


# This block runs only when you run the file directly (python river_tides.py),
# not when another script imports it. That lets other code reuse load_bar(), shifted() etc.
if __name__ == "__main__":
    main()
