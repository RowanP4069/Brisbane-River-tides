# Data sources: research notes

Research for roadmap items 12 (APIs instead of file downloads), 13 (2027 data) and 7/8 (measured water levels). Checked on 8 November 2026. Nothing here is used by the code yet. It records what exists, how to reach it, and what to watch out for.

## Summary

- **The 2027 data is already published.** The 2027 Brisbane Bar predictions are on data.qld.gov.au (added 3 September 2026), and the 2027 tidal planes PDF is on MSQ's site. Item 13 can be done now rather than in a rush in late December.
- **The Bar predictions have an API.** data.qld.gov.au serves every year's predictions through its query API, and a web page is allowed to call it directly. The download for item 12 can become one API call, and the same API could feed a page that picks its own day (item 3, option B).
- **Brisbane City Council publishes live river levels at eight places on the Brisbane River,** from the mouth of Breakfast Creek up to Moggill. It's open data (CC BY 4.0) with an API a web page can call directly. **But it only keeps the last 72 hours.** History for item 8 has to be collected by us, starting as soon as possible.
- **First comparison:** at Port Office, MSQ's official prediction matches the council gauge to within about 4 cm (standard deviation), with timing within 5 minutes, over the last 72 hours. On those three days, LAT was about **1.22 m below AHD** there.

## Item 12: the current downloads

| Data | Now | API? |
|---|---|---|
| Brisbane Bar predictions (`bar_2026_10min.csv`) | CSV downloaded by hand | **Yes.** It's in the data.qld.gov.au datastore, so it can be queried with `datastore_search` / `datastore_search_sql`. Pages may call it directly (CORS `*`). |
| Tidal planes (`stations.csv`) | Typed in by hand from MSQ's yearly PDF | **No.** It's only published as a PDF, and the table would have to be read from the PDF text. That's not worth automating for one update a year. |
| Watercourse line (`qld_watercourse_brisbane_river.geojson`) | `build_centreline.py --download` | **Already an API** (Queensland spatial ArcGIS REST service). |

Brisbane Bar predicted interval data, one resource per year:

| Year | Resource id | Rows |
|---|---|---|
| 2026 | `11f33b0e-953f-46f4-84a9-1aa0a779a5e7` | 52,560 (= 365 × 144, as expected) |
| 2027 | `458352c5-4038-4f55-a489-9ffa0e25af97` | **72,620.** That's more than one year of 10-minute values. Check for duplicates or extra days before using it (item 13). |

Example query: `https://www.data.qld.gov.au/api/3/action/datastore_search?resource_id=<id>&limit=5`. The columns are the same as in our CSV (`_id, Date, Time, Ind, Reading`). The values come back as text, and the rows aren't guaranteed to be in time order.

The one-resource-per-year layout means a year change still needs the new resource id. It could be looked up from the dataset (`package_show?id=brisbane-bar-tide-gauge-predicted-interval-data`) by matching the year in the resource name.

## Item 13: 2027 notes

- **Predictions:** see the table above.
- **Tidal planes:** the 2027 PDF is linked from <https://www.msq.qld.gov.au/tides/tidal-planes>. The Brisbane River rows are on page 2, and at a glance they match 2026. The Indooroopilly / Seventeen Mile Rocks lag reversal is still there (Indooroopilly +1:20 / +1:45, Seventeen Mile Rocks +1:20 / +1:20).
- **Bar MSL:** MSQ's tidal datum page gives a Bar MSL of **1.351 m** "used for the tidal predictions for 2027", while the planes table still lists 1.32 m. That affects the anomaly baseline (`MSL_Bar`). Decide which to use in item 13.

## Items 7/8: measured water levels

### Brisbane City Council telemetry

- **Datasets** on data.brisbane.qld.gov.au: the readings (wide format), `-observations` (one row per reading, easiest to use) and `-metadata` (gauge list).
- **Licence:** CC BY 4.0. Publisher: Brisbane City Council.
- **Access:** an Opendatasoft API, for example `/api/explore/v2.1/catalog/datasets/telemetry-sensors-rainfall-and-stream-heights-observations/records?where=gauge="E1855"`. **Web pages may call it directly (CORS `*`).**
- **Units and datum:** metres, AHD.
- **Time step:** 5 minutes, but many slots are empty. Over 72 hours, the river gauges filled 20–50 % of slots. Times are UTC in `measured`, and AEST in `measured_text`.
- **History: a rolling 72 hours only.**
- These are the same gauges BoM shows on its flood pages. The awaremate.app river-heights site shows BoM's copy of the Brisbane City gauge (540198 = E6749).

Gauges on the Brisbane River itself, listed downstream to upstream:

| Sensor | BoM no. | Name | Notes |
|---|---|---|---|
| E1594 | 540286 | Mouth of Breakfast Ck, Newstead | |
| E1857 | 540685 | Hawthorne AL | |
| E6749 | 540198 | Brisbane City Gauge AL | |
| E1855 | 540684 | Port Office Gauge | Same reach as MSQ's Port Office secondary place |
| E1856 | 540683 | St Lucia AL | |
| E1588 | 540274 | Mouth of Oxley Ck, Graceville | |
| E1765 | 540682 | Jindalee (BCC) AL | Lowest reading in 72 h was +0.10 m, against about −0.85 m downstream. **Check whether it reads the bottom of the tide.** |
| E1764 | 540201 | Moggill (BCC) AL | Lowest reading −0.07 m. Same question. |

The council also has dozens of creek gauges and rain gauges, which could be useful for item 9.

### MSQ (Maritime Safety Queensland) tide gauges

Listed on <https://www.msq.qld.gov.au/tides/open-data>. All are CC BY 4.0 and in metres above LAT.

- **Brisbane Bar near real time:** `https://opendata.tmr.qld.gov.au/Whyte_Island.txt`.
  - 1-minute readings covering about the last week, updated every 10 minutes. The data isn't checked, so it can contain errors.
  - **No CORS header,** so a web page can't fetch it directly; it would need a server-side step.
  - The datastore copy on data.qld.gov.au stopped in 2019. Use the file.
- **Brisbane Bar archived (measured, checked) data:** 10-minute, yearly files up to 2025, in the datastore.
- **Pinkenba (Gateway Bridge) archived measured data:** 10-minute, yearly up to 2025, in the datastore. MSQ has no near-real-time feed for Pinkenba.
- **Official predictions for Pinkenba and Port Office:** 10-minute series, also in the datastore. Port Office 2026 is resource `68b27a91-0163-4872-8433-d2765f6f670d`. These give us a free check of our own model at two places.

### Queensland Government storm tide monitoring (Coastal Data System)

Checked 2026-11-09, after seeing the Pinkenba Wharf chart embedded on a third-party site.

- **Live charts:** `https://apps.des.qld.gov.au/waves/graphs/<site>_tide.png`, 600×480 images showing actual, predicted and residual levels in m above LAT, with AHD and HAT marked. They're redrawn hourly. There's one for **Brisbane River (Pinkenba Wharf)**, `pinkenbawharf_tide.png`.
- **Pinkenba is a chart only.** There's no data file for it: it isn't in either CSV feed below, and it has no site page under qld.gov.au/tides (guessed URLs return 404, and directory listings return 403). The only Pinkenba data stays the yearly archive above. Reading values off the image would be fragile, so it isn't worth doing. If live Pinkenba matters later, ask the Coastal Impacts Unit whether `pinkenbawharf` could be added to the CSV feed.
- **Two 7-day CSV feeds** (CC BY 4.0, data.qld.gov.au "Coastal Data System – Near real time tide data" and "… storm tide data"):
  - `https://apps.des.qld.gov.au/data-sets/storm-tides/stdtide-7dayopdata.csv`, 24 sites
  - `https://apps.des.qld.gov.au/data-sets/storm-tides/tide-7dayopdata.csv`, 61 sites
  - Columns: `Site, Seconds, DateTime, Water Level, Prediction, Residual, Latitude, Longitude`. 10-minute steps, last 7 days, DateTime in AEST (checked against Seconds), m above LAT.
  - Near Brisbane: `whyteislandnx` (Brisbane Bar), plus the Moreton Bay sites `shorncliffe`, `scarborough`, `tangalooma`, `rabybay`, `birkdale`, `bananabank`, `goldcoast`, `coombabahst` and `goldenbeach`.
  - **Useful for:** the official residual at the Bar (a check on our weather baseline), and measured levels across Moreton Bay for roadmap item 15. Like the BCC data, it's only kept for 7 days, so archiving it would mean adding it to `collect_gauges.py`.

### Queensland water monitoring (WMIP), upstream gauges

- **Web service:** `https://water-monitoring.information.qld.gov.au/cgi/webservice.exe` (Kisters Hydstra JSON). It returns `"licence":"CC_40_BY"`.
- **No CORS header,** so it's for server-side or offline use only.
- **History:** long, decades at the main stations.
- **Stations of interest:**
  - **143001C Brisbane River at Savages Crossing** (below Wivenhoe): level and flow. Flow was about 5 m³/s on 6 November.
  - **1430096 Brisbane R at Worlds End Pocket, Fernvale.**
  - **1430912 St Lucia** and **1430126 Murarrie:** listed on the Brisbane River, but what they measure is not checked yet.
- For item 9, the tributaries (Bremer and Lockyer) are still to be found. Seqwater dam releases also need a source; none was found yet.

### BoM

BoM shows the council gauges on its flood pages, and runs Water Data Online. Its reuse terms are tighter than CC BY, and the council API is the original source of the same readings, so BoM isn't needed for now.

## First check: Port Office, measured vs predicted

Last 72 hours (5–8 Nov 2026): council gauge E1855 (AHD) compared with MSQ's official Port Office prediction (LAT), 396 readings:

- Prediction minus measured: **mean 1.216 m**, standard deviation 0.045 m (0.039 m with the prediction 5 minutes earlier).
- **What it means:** the official secondary-port prediction tracks the real river well at the city reach on ordinary days.
- **The offset:** LAT ≈ AHD − 1.22 m at Port Office. That figure also contains whatever the river was doing on those days (flow, weather). For the exact figure, look up the AHD height of the Port Office mark (PSM 130588, 6.518 m above LAT) on Queensland Globe and compare.

## Datum: getting gauges onto our LAT

- The council gauges read AHD, and our model is in each place's own LAT. Each gauge needs an offset.
- **The proper way:** MSQ's planes give each permanent mark's height above LAT, and Queensland Globe (survey control) gives the same mark's AHD height. The difference is the offset at that place. Marks with a LAT height listed:
  - Brisbane Bar PSM 88814
  - Pinkenba PSM 7632
  - Port Office PSM 130588
  - Goodna PSM 30537
  - Moggill PSM 54705
  - Kholo PSM 32752
- **The cross-check:** the mean of predicted minus measured over a few weeks, as above. If the two disagree by more than a few centimetres, find out why.

## Browser access (for live pages)

| Source | Page can fetch directly? |
|---|---|
| data.qld.gov.au datastore (predictions, MSQ archives) | Yes |
| Brisbane City Council telemetry | Yes |
| MSQ Bar near-real-time file | No (needs a server-side step) |
| WMIP | No (needs a server-side step) |

## Recommendations

1. **(Done 8 Nov 2026: `collect_gauges.py`, daily, to the `gauge-data` branch. It also saves the MSQ Bar feed.)** **Start collecting council river-gauge readings now.** History only exists for 72 hours, so every day not saved is lost. A small scheduled GitHub Action could save the eight river gauges daily. That's about 7,000 rows a day at most; it could live in the repo or on a separate data branch. This is the most time-sensitive finding.
2. **(Done 8 Nov 2026: `fetch_bar.py`, `data/bar_2027_10min.csv`.)** **Do item 13 soon.** The 2027 data is out. Sort out the 72,620-row question and the 1.32 vs 1.351 m Bar MSL while doing it.
3. **(Done the same way.)** **Item 12:** fetch the Bar predictions through the datastore API, and keep a copy in `data/` so builds don't depend on the API being up. Decide when doing item 13.
4. **Offline comparison (item 8):** start at Port Office. Compare three things there: our model, MSQ's official prediction and the measured level. Then work upriver with the council gauges. Use the MSQ Bar and Pinkenba archives for longer history near the mouth.
5. **(First version done 8 Nov 2026: the gauges page, council gauges only.)** **Item 7 (live page):** the council gauges and the prediction API both work from a page directly. The Bar's live reading would need a server-side step, or can be left out.
6. **Item 9:** WMIP gives upstream flow (Savages Crossing). Tributary gauges and dam releases still need finding.

## Open questions

- Do Jindalee and Moggill read the low tide, or does the sensor sit above it?
- Why does the 2027 Bar resource have 72,620 rows?
- What are the exact AHD heights of the PSMs (Queensland Globe)?
- What do WMIP 1430912 (St Lucia) and 1430126 (Murarrie) measure?
- What source is there for Seqwater dam releases and the tributary gauges?

## Sources

- Brisbane City Council telemetry (data.qld.gov.au listing): <https://www.data.qld.gov.au/dataset/telemetry-sensors-rainfall-and-stream-heights>
- The same datasets and API: <https://data.brisbane.qld.gov.au/explore/dataset/telemetry-sensors-rainfall-and-stream-heights-observations>
- MSQ open data index: <https://www.msq.qld.gov.au/tides/open-data>
- MSQ tidal planes (2026 and 2027 PDFs): <https://www.msq.qld.gov.au/tides/tidal-planes>
- MSQ tidal datum information (MSL used for 2027): <https://www.msq.qld.gov.au/tides/tidal-datum-information>
- Brisbane Bar predicted interval data: <https://www.data.qld.gov.au/dataset/brisbane-bar-tide-gauge-predicted-interval-data>
- Brisbane Bar near real time: <https://www.data.qld.gov.au/dataset/brisbane-bar-tide-gauge-near-real-time-data>
- Brisbane Bar archived recordings: <https://www.data.qld.gov.au/dataset/brisbane-bar-tide-gauge-archived-interval-recordings>
- Pinkenba archived recordings: <https://www.data.qld.gov.au/dataset/pinkenba-tide-gauge-archived-interval-recordings>
- Port Office predicted interval data: <https://www.data.qld.gov.au/dataset/port-office-brisbane-river-tide-gauge-predicted-interval-data>
- Queensland water monitoring portal: <https://water-monitoring.information.qld.gov.au/>
- Brisbane River at Brisbane City (BoM data via awaremate): <https://awaremate.app/river-heights/qld/brisbane-river-at-brisbane-city-540198/>
