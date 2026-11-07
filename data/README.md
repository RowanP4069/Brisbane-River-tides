# data/

Input data for `river_tides.py`. These files are committed to the repo on purpose. The online sources can be revised, replaced or taken down, and a committed copy keeps every tagged version reproducible.

Placeholders marked `TODO` are things I couldn't confirm from here. Fill them in from your browser history or download folder.

| File | What it is | Origin |
|---|---|---|
| `bar_2026_10min.csv` | Brisbane Bar predicted water level, 10-minute interval, 2026 | Downloaded from MSQ / Queensland open data |
| `stations.csv` | Secondary-port corrections (lag, ratio) and chainage per station | Hand-built from the MSQ 2026 tidal planes PDF; chainage from `build_centreline.py` |
| `qld_watercourse_brisbane_river.geojson` | Brisbane River segments of the QLD watercourse lines layer, as downloaded | QLD Department of Resources spatial service |
| `centreline.csv` | Single ordered river centreline, Brisbane Bar gauge upstream, with chainage | Derived by `build_centreline.py` from the file above |

---

## `bar_2026_10min.csv`

**Source**

- 2026 resource page (Queensland Government open data portal, dataset *Brisbane Bar tide gauge — predicted interval data*):
  https://www.data.qld.gov.au/dataset/brisbane-bar-tide-gauge-predicted-interval-data/resource/11f33b0e-953f-46f4-84a9-1aa0a779a5e7
- MSQ open data index (lists every station's interval and high/low files): https://www.msq.qld.gov.au/tides/open-data
- Publisher: Maritime Safety Queensland (Department of Transport and Main Roads), tides@msq.qld.gov.au.
- Predictions are produced by the Bureau of Meteorology and published by MSQ. BoM's Queensland tide tables:
  https://www.bom.gov.au/oceanography/projects/ntc/qld_tide_tables.shtml
- Original filename as downloaded: `TODO` (likely `p046046a_brisbane-bar_2026_10min.csv`).
- Retrieved: `TODO` (YYYY-MM-DD).
- SHA-256 of the committed file (computed 2026-11-07): `b14aa74150adffaf2deeb054fbf4079a83bfe96dda7b8079184ad51686c355b0`. Size 1,618,284 bytes. Check with `sha256sum data/bar_2026_10min.csv`.

**Licence**

- Creative Commons Attribution 4.0 (CC BY 4.0), as shown on the 2026 resource page and checked 2026-11-07.
- Attribution: "Contains data from Maritime Safety Queensland, © State of Queensland (Department of Transport and Main Roads), licensed under CC BY 4.0."

**Format (checked against the committed file, 2026-11-07)**

- Header: `_id,Date,Time,Ind,Reading`. `_id` is a datastore row number (1 to 52,560) and is in the downloaded file. Only `Date`, `Time` and `Reading` are needed.
- Encoding is UTF-8 **with a BOM**. Read with `encoding="utf-8-sig"`, otherwise the first column name becomes `﻿_id`.
- `Date` is `DD/MM/YYYY` (day-first), e.g. `01/01/2026`.
- `Time` is `HH:MM` at 10-minute steps, starting at `00:00` on 1 January 2026.
- `Ind` is `9` on every row. `TODO`: its meaning is not documented here. Check the "Description—Brisbane Bar…" resource in the same dataset.
- `Reading` is in metres, to 3 decimal places. Range in 2026: 0.233 to 2.789 m.
- 52,560 data rows (365 days × 144 per day), from `01/01/2026 00:00` to `31/12/2026 23:50`. Every step is exactly 10 minutes, with no gaps or duplicates. Use this as a load check.
- Times are AEST (UTC+10, no daylight saving), kept as naive local time.
- Datum is assumed to be Queensland Port Datum, LAT (1992), which is what the MSQ tidal planes use. `TODO`: confirm in the "Description—Brisbane Bar…" resource.

**Processing**

None. The file is stored as downloaded, apart from the rename. All parsing happens in `load_bar()`.

---

## `stations.csv`

**Source**

- *Semidiurnal Tidal Planes — 2026*, Maritime Safety Queensland. Heights are above Queensland Port Datum, LAT (1992).
  https://www.msq.qld.gov.au/_/media/tmronline/msqinternet/msqfiles/home/tides/tidal-planes/2026-semidiurnal-tidal-planes.pdf
- MSQ tidal planes page: https://www.msq.qld.gov.au/tides/tidal-planes
- Retrieved: `TODO`. The PDF was attached to a Claude session on 2026-11-07, so retrieval was on or before that date.
- Licence: `TODO`. Check the MSQ site copyright page.

**Derivation**

This file is hand-built, not a copy of anything published, so record any change to it here.

- 13 stations, from Brisbane Bar to Kholo Creek. Mt Crosby Weir is not in the MSQ table, so the model stops at Kholo Creek.
- `lat` and `lon` are as given in the tidal planes table, rounded to about 1 arc-minute (up to ~1.6–1.85 km), except Brisbane Bar (see Changes).
- `lag_hw_min` and `lag_lw_min` are the published high-water and low-water time differences relative to Brisbane Bar, in minutes.
- `lag_min` is the mean of `lag_hw_min` and `lag_lw_min`. It is the only lag column the script reads (v0.1.0).
- `ratio` is the height ratio relative to Brisbane Bar:
  - Pinkenba to Indooroopilly: the published ratio.
  - Stations marked `**` in the PDF (non-linear transfer, no ratio published): **derived** as the mean of the spring and neap range ratios against the Bar. The Bar values used were spring range 1.80 m and neap range 1.03 m. This is an estimate, and the spring and neap ratios diverge upriver (Moggill is about 1.14 vs 1.38).
- `chainage_km` is distance along the river from the Brisbane Bar gauge, measured on `centreline.csv`. Each station's `lat`/`lon` is snapped to the nearest point on the centreline, and the result is rounded to 0.1 km. Written by `python build_centreline.py --no-fetch --write-stations`. Because the positions are rounded to ~1 arc-minute, each value carries roughly ±1 km of uncertainty. Tennyson is the weakest snap: about 1.1 km off the line, with another reach about 0.8 km further away.
- Header: `name,lat,lon,chainage_km,lag_min,lag_hw_min,lag_lw_min,ratio,note`.
- `note` records the provenance of each ratio (published, or derived with the spring and neap values used).
- 14 rows: the 13 stations plus a `Mt Crosby Weir` placeholder with empty values, which the script skips. Fill it in only from a source.
- Line endings are CRLF. `build_centreline.py` keeps them when it rewrites the file.
- SHA-256 (2026-11-07, after the changes below): `c8a89ca16b5238c538483e7591e8a9baf5bd07d740dbf30c92cae9906db3c6c3`.

**Changes**

- 2026-11-07: `chainage_km` replaced with distance measured along the river centreline. The old values were straight-line distances between consecutive stations and understated river distance by up to about 34 % (Kholo Creek 56.6 → 75.8 km, Moggill Ferry 49.2 → 68.6 km). Boat Passage now snaps to 0.0 km (it was 3.7). This does not affect the model, because its lag is 0 and its ratio is 1, the same as the Bar.
- 2026-11-07: Brisbane Bar `lat`/`lon` changed from -27.3667, 153.1667 to -27.4016, 153.1574, the current gauge at Whyte Island (see `centreline.csv`, Gauge position). The old value matches the historical "West Inner Bar" position listed by PSMSL and GLOSS.

**Known quirks**

- Lags are not strictly monotonic. Seventeen Mile Rocks (80 min) is earlier than Indooroopilly (92.5 min). This comes from the published table, not a transcription error.

---

## `qld_watercourse_brisbane_river.geojson`

**Source**

- *Watercourse lines - Queensland*, Department of Resources, State of Queensland. Dataset series: https://www.data.qld.gov.au/dataset/hydrographic-features-queensland-series
- Downloaded from the ArcGIS service `InlandWaters/WaterCoursesAndBodies/MapServer`, layer 33, by `build_centreline.py` with the query `name='Brisbane River'` inside the box 152.70–153.25 E, -27.65 to -27.30.
- Retrieved: 2026-11-07.
- SHA-256: `3ac08dd90217c46caf1375adab40b9e8efe4e83ccc2c80d5bc374bc2f184eef8`. Size 132,135 bytes.

**Licence**

- Creative Commons Attribution 4.0 (CC BY 4.0), as shown on the data.qld.gov.au listing for the North East Coast drainage division subset. The ArcGIS service metadata says the dataset "has no use limitations". `TODO`: confirm the licence on the statewide resource page.
- Attribution: "Contains data from Watercourse lines - Queensland, © State of Queensland (Department of Resources), licensed under CC BY 4.0."

**Format**

- GeoJSON FeatureCollection, WGS84 lon/lat, 290 line features as returned by the service.
- Most segments are `feature_type` "Connector" (the routing line drawn through the river's water area), captured from 50 cm SE Qld orthophotography, some from 10 cm Brisbane South imagery.

**Processing**

None. Stored exactly as returned. All processing happens in `build_centreline.py`.

---

## `centreline.csv`

**Derivation** (`build_centreline.py`)

1. Segments are joined at shared end points into a network.
2. The main stem is the shortest path from the mouth end (the network node nearest the gauge) to the node farthest along the network (152.69874 E, -27.50000, where the river leaves the download box, upstream of Mt Crosby). This drops 21 segments (5.49 km): side channels around islands, including the split channel near 152.79–152.80 E, -27.54 to -27.56, and pieces not connected to the main stem.
3. A 1,131 m straight segment joins the gauge to the mouth end of the line.
4. Chainage is cumulative length along the line on a local flat projection centred on 27.5 S (scale error under 0.2 % over this area).

- Header: `lon,lat,chainage_km`. 957 vertices, ordered from the gauge upstream. Chainage 0 at the gauge, 116.74 km at the upstream end.
- Gauge position: Brisbane Bar (Whyte Island), 27° 24.096′ S, 153° 9.444′ E, from https://www.qld.gov.au/environment/coasts-waterways/beach/tide-sites/brisbane-bar (checked 2026-11-07). An older position, -27.36666, 153.16666 ("West Inner Bar"), is listed by PSMSL and GLOSS (https://psmsl.org/data/obtaining/stations/822.php). It is rounded to whole arc-minutes, out in the bay about 4 km away, and appears to be historical.
- SHA-256 (built 2026-11-07): `f5e7a1c26efcf37a7443080df86fe8e11a6b2c119f1f70fa21bff2b300d1588f`. Size 29,911 bytes.
- Rebuild with `python build_centreline.py --no-fetch`. The output should match the checksum above.

**Known limitations**

- The centreline follows the mapped main channel. It is not a navigation channel or thalweg.
- Station chainage inherits the ~1 km uncertainty of the station positions (see `stations.csv`). `build_centreline.py` only rewrites `stations.csv` when run with `--write-stations`.

---

## Updating

When a new year's file is added, or `stations.csv` changes:

1. Add the file and update the relevant section above: source URL, retrieval date, checksum, and any processing.
2. Commit the data and this README together, with a message saying what changed.
3. If the change alters the output, bump the minor version tag.
