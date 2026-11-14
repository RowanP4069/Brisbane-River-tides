# data/

Input data for `river_tides.py`. These files are committed to the repo on purpose. The online sources can be revised, replaced or taken down, and a committed copy keeps every tagged version reproducible.

Placeholders marked `TODO` are things I couldn't confirm from here. Fill them in from your browser history or download folder.

| File | What it is | Origin |
|---|---|---|
| `bar_2026_10min.csv` | Brisbane Bar predicted water level, 10-minute interval, 2026 | Downloaded from MSQ / Queensland open data |
| `stations.csv` | Secondary-port corrections (lag, ratio) and chainage per station | Hand-built from the MSQ 2026 tidal planes PDF; chainage from `build_centreline.py` |
| `qld_watercourse_brisbane_river.geojson` | Brisbane River segments of the QLD watercourse lines layer, as downloaded | QLD Department of Resources spatial service |
| `centreline.csv` | Single ordered river centreline, Brisbane Bar gauge upstream, with chainage | Derived by `build_centreline.py` from the file above |
| `features.csv` | Gravel runs and landmarks between Kholo Creek and the old weir ruin | Field visits and OpenStreetMap |
| `observations.csv` | What field visits showed at those features (run running or drowned, water surface) | Field visits, with photos and videos kept privately |

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

## `bar_2027_10min.csv`

Same source, licence, attribution and format as `bar_2026_10min.csv` above, for 1 January to 31 December 2027.

- **How it was made:** `python fetch_bar.py --year 2027`, on 2026-11-08, from the data.qld.gov.au datastore API (resource `458352c5-4038-4f55-a489-9ffa0e25af97`, created 2026-09-03). That day the resource's download link returned a web page instead of the CSV, so the API was used instead.
- **Processing:** the API table had 72,620 rows. Rows from 14 August to 31 December 2027 were there twice, with identical values. `fetch_bar.py` dropped the 20,060 exact duplicates and renumbered `_id`. Nothing else was changed.
- **Check:** `fetch_bar.py --year 2026` rebuilds the committed 2026 file byte for byte (checked 2026-11-08).
- 52,560 rows, every step exactly 10 minutes. `Ind` is `9` on every row. `Reading` ranges from 0.197 to 2.809 m.
- **Mean reading:** 1.351 m, matching the MSL MSQ says it used for the 2027 predictions. The 2026 file averages 1.347 m. The model's `MSL_Bar` stays at the tidal planes' 1.32 m (see `stations.csv`). The difference shifts upriver heights by about 1 cm at most.
- SHA-256: `1816a88b27b9027d9fedbac32f85093cf4a3451766e4f5dd3a0fd11a4383fe83`. Size 1,618,284 bytes.

`river_tides.py` reads every `data/bar_YYYY_10min.csv` by default and joins them, so a window can cross New Year.

---

## `gauges.csv`

The eight Brisbane City Council river gauges shown on the gauges page, downstream to upstream. Made by `python build_gauges.py --download` on 2026-11-08.

- **Source:** the council's gauge list, dataset *Telemetry sensors — Rainfall and Stream heights* (metadata), © Brisbane City Council, CC BY 4.0. <https://data.brisbane.qld.gov.au/explore/dataset/telemetry-sensors-rainfall-and-stream-heights-metadata>
- **Columns:** `sensor_id`, `bom_no` (the BoM station number), `name`, `lat`, `lon`, `datum` and `unit` are as published. `short` is our short label.
- **Derived columns:** `chainage_km` is each gauge projected onto the nearest point of `centreline.csv`, and `offset_m` is how far the gauge is from that point. The offsets are 105–279 m: the gauges are on the bank or at creek mouths, while the centreline follows the middle of the river.
- The gauge readings themselves are not stored here. The page fetches them live, and `collect_gauges.py` archives them on the `gauge-data` branch.

---

## `ramps.csv`

Public boat ramps on the Brisbane River itself, from the mouth to the old weir ruin below Mt Crosby (km 87.4, the upper limit for reports), shown on the Report the flow page as places to find on the map. They're location references only: lanes, facilities and whether a ramp is usable at low tide are left out. Made by `python build_report.py --ramps` on 2026-11-09.

- **Brisbane City Council (14 ramps):** dataset *Boat Ramp locations*, © Brisbane City Council, CC BY 4.0. <https://data.brisbane.qld.gov.au/explore/dataset/boat-ramp-locations>. Of its 39 ramps, only those within 350 m of the centreline are kept; the rest are on the bay or up creeks (Breakfast, Norman, Oxley and Bulimba creeks). `name` is the council's street and suburb, plus "(canoe ramp)" where the council says so, except Caringal Dr, Karana Downs, which is named Kookaburra Park (`RAMP_NAMES` in `build_report.py`).
- **Maritime Safety Queensland (3 ramps: Goodna, Barellan Point, Colleges Crossing):** the council's list stops at its boundary, and Ipswich City Council's open data has no ramp list (checked 2026-11-09). These are read off the boat-ramp symbols on maps BR-2 and BR-1 of *Beacon to Beacon Guide: Brisbane River and Bremer River* (2018), © State of Queensland (Department of Transport and Main Roads), CC BY 4.0, using the map's 1-minute grid. Checked against two ramps the council also lists: the Jindalee symbol (BR-2) lands 15 m and the Kookaburra Park symbol (BR-1) 20 m from the council's positions. Goodna and Barellan Point match OpenStreetMap's slipways to 0.1 km. The positions are in `GUIDE_RAMPS` in `build_report.py`.
- **Columns:** `name`, `lat`, `lon`, `source` (council asset id, or the guide map). `km` is the ramp projected onto `centreline.csv`.

---

## `features.csv`

Fixed things on the river that observations refer to: gravel runs, structures and landmarks between Kholo Creek (km 75.8, where the predictions stop) and the old weir ruin (km 87.4). Started 2026-11-14.

Between Kholo Creek and the ruin the head of the tide is not a fixed point. It moves between the gravel run under the Colleges Crossing road bridge and the run below the ruin: a run is drowned when the tide is above it, and runs one way, fresh, when the tide is below it. These runs stay put between big floods, so `last_seen` records when each was last confirmed in place, and a new survey after a major flood should update them.

- **Sources:** field visits by the project owner (positions read from photo GPS, rounded to about 10 m), and OpenStreetMap for the road bridge, the pipe crossing, the weir ruin and the power lines (© OpenStreetMap contributors, ODbL, <https://www.openstreetmap.org/copyright>; looked up 2026-11-14). Where a feature crosses the river, `lat`/`lon` is where its OpenStreetMap line crosses `centreline.csv`.
- **Power lines** are listed as landmarks: they show in photos and give a check on where a photo was taken and which way it faces.
- **Columns:** `feature_id` (used by `observations.csv`), `kind`, `name`, `km` (on `centreline.csv`), `lat`, `lon`, `description`, `source`, `last_seen` (date the feature was last seen in place, blank if not yet checked on the ground), `ref_media` (file name of a reference photo or video; the media themselves are kept privately, not in this repository).

---

## `observations.csv`

What field visits showed, one row per thing seen: whether a gravel run was running or drowned, or what the water surface looked like. Started 2026-11-14. The flow reports (which way the water was moving) are a separate record on the `reports` branch.

- **What is recorded:** what was seen, not what it means. For example, calm water above a run is recorded as `water_surface` `calm`, without claiming the tide reached it: it may be a pool held up by the run. Whether a run is drowned is judged at the run itself. Conclusions drawn from these rows (such as the Kholo Creek level that drowns each run) are kept with the project's notes, not here.
- **`kholo_min_m`, `kholo_max_m`:** the predicted level at Kholo Creek (m above LAT) over the observation's time span, from this project's model (`river_tides.heights()`) and that year's Brisbane Bar predictions. For 2023 those come from MSQ's 2023 file on data.qld.gov.au (download only; not stored here). It is a yardstick, not a prediction at the run: the model stops at Kholo Creek.
- **Values:** `quantity` is `run_state` (`running`, `marginal` or `drowned`), `water_surface` (`calm`, `rippled`, ...) or `high_water_time` (the observed time of high water, `YYYY-MM-DD HH:MM`, a test of hypothesis H1 in `docs/hypotheses.md`). `confidence` is `certain`, `likely` or `unsure`, or `excluded` for a test that doesn't count under the hypothesis's rules.
- **Columns:** `obs_id` (date and number), `time_from_aest`, `time_to_aest`, `feature_id` (from `features.csv`, blank if none), `km_from`, `km_to`, `quantity`, `value`, `confidence`, `kholo_min_m`, `kholo_max_m`, `evidence` (media file names, kept privately, and any flow reports), `observer`, `notes`.

---

## `stations.csv`

**Source**

- *Semidiurnal Tidal Planes — 2026*, Maritime Safety Queensland. Heights are above Queensland Port Datum, LAT (1992).
  https://www.msq.qld.gov.au/_/media/tmronline/msqinternet/msqfiles/home/tides/tidal-planes/2026-semidiurnal-tidal-planes.pdf
- MSQ tidal planes page: https://www.msq.qld.gov.au/tides/tidal-planes
- **2027 check (2026-11-08):** the Brisbane River rows of *2027 Semidiurnal and diurnal tidal planes* (Brisbane Bar to Kholo Creek, 13 rows) are identical to 2026. That includes the Indooroopilly / Seventeen Mile Rocks lag reversal, so no change was needed.
- Retrieved: `TODO`. The PDF was attached to a Claude session on 2026-11-07, so retrieval was on or before that date.
- Licence: Creative Commons Attribution 4.0 (CC BY 4.0), by default. Checked 2026-11-08: MSQ refers to the Queensland Government *Open Data, Information Sharing, Access and Use Policy*, which makes CC BY 4.0 the default licence for government data:
  https://www.forgov.qld.gov.au/information-technology/queensland-government-enterprise-architecture-qgea/qgea-directions-and-guidance/qgea-policies-standards-and-guidelines/open-data-information-sharing-access-and-use-policy
  MSQ's open data page (https://www.msq.qld.gov.au/tides/open-data) says tide data is published "as part of the Queensland Government's Open Data initiative". Neither the PDF nor the tidal planes page states a licence of its own, so this rests on the policy default.
- Attribution: "Contains data from Maritime Safety Queensland, © State of Queensland (Department of Transport and Main Roads), licensed under CC BY 4.0."

**Derivation**

This file is hand-built, not a copy of anything published, so record any change to it here.

- 13 stations, from Brisbane Bar to Kholo Creek. Mt Crosby Weir is not in the MSQ table, so the model stops at Kholo Creek.
- `lat` and `lon` are as given in the tidal planes table, rounded to about 1 arc-minute (up to ~1.6–1.85 km), except Brisbane Bar (see Changes).
- `lag_hw_min` and `lag_lw_min` are the published high-water and low-water time differences relative to Brisbane Bar, in minutes.
- `lag_min` is the mean of `lag_hw_min` and `lag_lw_min`. It is the only lag column the script reads (v0.1.0).
- `ratio` is the height ratio relative to Brisbane Bar:
  - Pinkenba to Indooroopilly: the published ratio.
  - Stations marked `**` in the PDF (non-linear transfer, no ratio published): **derived** as the mean of the spring and neap range ratios against the Bar. The Bar values used were spring range 1.80 m and neap range 1.03 m. This is an estimate, and the spring and neap ratios diverge upriver (Moggill is about 1.14 vs 1.38).
  - Reviewed 2026-11-07 (v0.3.0): the spring-only range ratio was considered and rejected. It is exact at springs but understates neap swings by up to ~22 % (Kholo); the mean is within about ±12 % in both regimes. A ratio that varies with the Bar's current range is a candidate v0.4 item.
- `msl_m` is mean sea level from the same table, in metres above the station's **own** local LAT. Added in v0.3.0 for the absolute-height baseline.
- `range_m` is the spring range, MHWS − MLWS, from the same table. Added in v0.3.0 as a reference column; the script does not use it for the ratio.
- `chainage_km` is distance along the river from the Brisbane Bar gauge, measured on `centreline.csv`. Each station's `lat`/`lon` is snapped to the nearest point on the centreline, and the result is rounded to 0.1 km. Written by `python build_centreline.py --write-stations`. Because the positions are rounded to ~1 arc-minute, each value carries roughly ±1 km of uncertainty. Tennyson is the weakest snap: about 1.1 km off the line, with another reach about 0.8 km further away.
- Header: `name,lat,lon,chainage_km,lag_min,lag_hw_min,lag_lw_min,ratio,msl_m,range_m,note`.
- `note` records the provenance of each ratio (published, or derived with the spring and neap values used).
- 14 rows: the 13 stations plus a `Mt Crosby Weir` placeholder with empty values, which the script skips. Fill it in only from a source.
- Line endings are CRLF. `build_centreline.py` keeps them when it rewrites the file.
- SHA-256 (2026-11-07, after the changes below): `f03fceac0c02e605e7ea11cdb396aa23c27e0e7f35ddded0c2262012f0d6e1fd`.

**Changes**

- 2026-11-07 (v0.3.0): added `msl_m` and `range_m` from the MSQ 2026 tidal planes table. No existing values changed. Lags and published ratios were re-checked against the same table and all match.
- 2026-11-07: `chainage_km` replaced with distance measured along the river centreline. The old values were straight-line distances between consecutive stations and understated river distance by up to about 34 % (Kholo Creek 56.6 → 75.8 km, Moggill Ferry 49.2 → 68.6 km). Boat Passage now snaps to 0.0 km (it was 3.7). This does not affect the model, because its lag is 0 and its ratio is 1, the same as the Bar.
- 2026-11-07: Brisbane Bar `lat`/`lon` changed from -27.3667, 153.1667 to -27.4016, 153.1574, the current gauge at Whyte Island (see `centreline.csv`, Gauge position). The old value matches the historical "West Inner Bar" position listed by PSMSL and GLOSS.

**Known quirks**

- Lags are not strictly monotonic. Seventeen Mile Rocks (80 min) is earlier than Indooroopilly (92.5 min). This comes from the published table, not a transcription error.
  - It is almost all low water: HW is +1 20 at both places, while LW goes from +1 45 (Indooroopilly) to +1 20 (Seventeen Mile Rocks).
  - Checked 2026-11-08: every Brisbane River row is identical in the 2025 and 2026 *Semidiurnal Tidal Planes* (the only change is the Port Office benchmark), so this is a long-standing value, not a new typo.
  - Seventeen Mile Rocks and every place above it are marked `**`, which the PDF defines as "Tidal planes determined through non-linear tidal transfer. Contact MSQ Tidal Unit for further information."
  - Query emailed to the MSQ Tidal Unit on 2026-11-08 (how the two places were derived, and how to use `**` time differences). Record the reply here.

**Known limitations**

- **No common vertical datum.** Each station's heights (including `msl_m`) are above its own local LAT, not a shared reference. MSL "falls" from 1.43 m at Tennyson to 1.10 m at Kholo, but because the datums differ this says nothing reliable about the real water-surface gradient. Absolute heights built from `msl_m` are fine to display per point, but must not be differenced between points; the surface-slope proxy uses the anomaly instead.
- **Tidal asymmetry upstream.** HW and LW lags differ (by up to 25 min at Indooroopilly and 20 min at Kholo), and MLWS falls faster than MHWS upriver. The script uses one lag (`lag_min`, the mean) and one ratio per station, so it scales the Bar's curve shape rather than reproducing the steeper flood and longer ebb. Candidate v0.4 item: separate HW and LW lags.
- **Heights below LAT upstream at big springs.** The `**` stations use the mean of the spring and neap ratios, which overstates the spring swing (Kholo: 1.25 used vs 1.10 at springs). Most of the excess falls below MSL, so on large spring tides the model can go below local LAT. Example: 2026-11-08, Kholo minimum −0.14 m against a published MLWS of 0.19 m. Accepted for v0.3.0 (direction proxies are barely affected) and labelled on the page. Fix candidate (v0.4): ratio interpolated between spring and neap values using the Bar's current range.
- **Lag runs backwards between Indooroopilly and Seventeen Mile Rocks** (km 37.6 → 44.7, lag 92.5 → 80 min, from the published table). Interpolated along chainage, the tide appears to arrive earlier further upstream across this reach. Left as published and labelled on the page.
- **Windows at the edges of the year.** Upstream points read the Bar up to 160 min (Kholo's lag) before each frame, and the window includes its end frame. With only the 2026 file, a window must therefore start at 2026-01-01 02:40 or later and end by 2026-12-31 23:50. So `--start 2026-01-01` fails, and so does `--start 2026-12-31` with the default 24 h (its last frame is 2027-01-01 00:00); use e.g. `--hours 23.5` there, or add the next year's file. The script stops with a message saying which end is short.

---

## `qld_watercourse_brisbane_river.geojson`

**Source**

- *Watercourse lines - Queensland*, Department of Resources, State of Queensland. Dataset series: https://www.data.qld.gov.au/dataset/hydrographic-features-queensland-series
- Downloaded from the ArcGIS service `InlandWaters/WaterCoursesAndBodies/MapServer`, layer 33, by `build_centreline.py` with the query `name='Brisbane River'` inside the box 152.70–153.25 E, -27.65 to -27.30.
- Retrieved: 2026-11-07.
- SHA-256: `3ac08dd90217c46caf1375adab40b9e8efe4e83ccc2c80d5bc374bc2f184eef8`. Size 132,135 bytes.

**Licence**

- Creative Commons Attribution 4.0 (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/). Confirmed 2026-11-08 on the dataset series page (https://www.data.qld.gov.au/dataset/hydrographic-features-queensland-series), which states this licence explicitly. Also shown on the listing for the North East Coast drainage division subset; the ArcGIS service metadata says the dataset "has no use limitations".
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
- Rebuild with `python build_centreline.py` (it reuses the saved download; `--fetch` downloads it again and replaces it). The output should match the checksum above.

**Known limitations**

- The centreline follows the mapped main channel. It is not a navigation channel or thalweg.
- Station chainage inherits the ~1 km uncertainty of the station positions (see `stations.csv`). `build_centreline.py` only rewrites `stations.csv` when run with `--write-stations`.

---

## Updating

When a new year's file is added, or `stations.csv` changes:

1. For a new year of Bar predictions, once MSQ publishes it (2027 appeared in September 2026), run `python fetch_bar.py --year YYYY`. Check the new tidal planes PDF against `stations.csv`. Then add the file and update the relevant section above: source URL, retrieval date, checksum, and any processing.
2. Commit the data and this README together, with a message saying what changed.
3. If the change alters the output, bump the minor version tag.
