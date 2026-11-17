# Measured water levels: Brisbane River (gauge-data branch)

This branch holds **data only**. It's added to by `collect_gauges.py` on the `main` branch: once a day by the `collect-gauges` workflow, and every 15 minutes for BoM river heights by the `collect-bom` workflow. The project's code and documentation are on `main`; see `docs/data-sources.md` there for how the sources were chosen.

The sources keep only a short window (72 hours for the council gauges, about a week for the Bar, 7 days for the storm tide gauges), so this branch is the long-term record.

## Files

One CSV per source per month. Columns: `time_aest, gauge, value_m`.

- Times are AEST (UTC+10, no daylight saving), to the minute.
- Values are stored **as received**: no datum change, no cleaning, gaps left as gaps. If a reading comes back later with a different value, the newer value replaces it.

### `bcc/YYYY-MM.csv`: Brisbane City Council telemetry

Values are metres **AHD**. Readings come in 5-minute slots, and many slots are empty. Gauges, downstream to upstream:

| gauge | BoM no. | name |
|---|---|---|
| E1594 | 540286 | Mouth of Breakfast Ck, Newstead |
| E1857 | 540685 | Hawthorne AL |
| E6749 | 540198 | Brisbane City Gauge AL |
| E1855 | 540684 | Port Office Gauge |
| E1856 | 540683 | St Lucia AL |
| E1588 | 540274 | Mouth of Oxley Ck, Graceville |
| E1765 | 540682 | Jindalee (BCC) AL |
| E1764 | 540201 | Moggill (BCC) AL |

The council publishes these readings raw. Brisbane City Council doesn't warrant their accuracy, and they're passed on to the Bureau of Meteorology's flood warning network.

### `msq_bar/YYYY-MM.csv`: MSQ Brisbane Bar near real time

Values are metres above **LAT** (Queensland Port Datum). Gauge `046046A` is Brisbane Bar (Whyte Island), with 1-minute readings. MSQ describes this data as raw and unvalidated; its checked archive is published yearly on data.qld.gov.au.

### `cds/YYYY-MM.csv`: Queensland Government storm tide gauges

Collected from 2026-11-09. Columns: `time_aest, gauge, value_m, prediction_m`. Values are metres above **LAT**, every 10 minutes; `prediction_m` is the official tide prediction for that gauge, so measured minus predicted is the residual (weather and surge). Slots with no reading yet are skipped. The source keeps 7 days. Gauges, roughly north to south:

| gauge | site |
|---|---|
| goldenbeach | Golden Beach (Pumicestone Passage) |
| hallsbay | Halls Bay (Pumicestone Passage) |
| donnybrook | Donnybrook (Pumicestone Passage) |
| scarborough | Scarborough (Moreton Bay) |
| tangalooma | Tangalooma (Moreton Bay) |
| shorncliffe | Shorncliffe (Moreton Bay) |
| whyteislandnx | Brisbane Bar (Whyte Island) |
| birkdale | Birkdale (Moreton Bay) |
| rabybay | Raby Bay (Moreton Bay) |
| bananabank | Banana Bank (Moreton Bay) |
| coombabahst | Coombabah (Broadwater) |
| goldcoast | Gold Coast Seaway (Southport) |

### `bom/YYYY-MM.csv`: Bureau of Meteorology river heights

Collected from 2026-11-17. Columns: `time_aest, gauge, value_m, datum`. Every gauge on the Brisbane River itself (station names "Brisbane River at ...") in BoM's Brisbane basin river height bulletin, IDQ60286, fetched from BoM's public anonymous FTP (`ftp://ftp.bom.gov.au/anon/gen/fwo/IDQ60286.html`). `gauge` is the BoM station number; `bom/stations.csv` gives each one's name and datum.

- `datum` is as the bulletin gives it: `AHD`, or `LGH` (local gauge height, metres above the gauge's own zero). 540063 Colleges Crossing is LGH with gauge zero 0.00 m AHD (BoM flood warning network, Section 6), so its values are m AHD.
- The bulletin holds only each gauge's **latest** reading, and many gauges report on each 0.05 m step rather than on a clock. So this series is only as complete as the 15-minute runs, which GitHub sometimes delays or skips: readings between runs are missed. BoM's web table for a gauge keeps about two weeks; gaps can be filled from it by hand in a browser (it is never fetched by script).
- The bulletin gives the reading time as e.g. "02.14PM Tue"; the date is the latest such day at or before the bulletin's issue time. Readings that would be more than 6 days old are skipped.
- Some gauges here are the same instruments as in `bcc/` (e.g. 540683 St Lucia = E1856), through a different route.

## Licence and attribution

The BCC, MSQ and storm tide sources are licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The files here are unchanged copies, merged by date, except that for the storm tide gauges the residual column (measured minus predicted) and empty slots are left out.

- Telemetry sensors: Rainfall and Stream heights © Brisbane City Council, CC BY 4.0. <https://data.brisbane.qld.gov.au/explore/dataset/telemetry-sensors-rainfall-and-stream-heights-observations>
- Brisbane Bar tide gauge near real time data © State of Queensland (Maritime Safety Queensland, Department of Transport and Main Roads), CC BY 4.0. <https://www.data.qld.gov.au/dataset/brisbane-bar-tide-gauge-near-real-time-data>
- Coastal Data System – Near real time storm tide data © State of Queensland (Department of Environment, Tourism, Science and Innovation), CC BY 4.0. <https://www.data.qld.gov.au/dataset/coastal-data-system-near-real-time-storm-tide-data>

**Not for navigation or flood warnings.** For current warnings, use the Bureau of Meteorology.
- River heights from the Bureau of Meteorology, © Commonwealth of Australia, river height bulletin IDQ60286. The bulletin says its material is licensed under the Creative Commons Attribution Australia Licence unless otherwise noted, and that most river height data is supplied to BoM by other agencies, whose terms apply. No other terms are noted for these gauges (checked 2026-11-17); they will be removed if a supplying agency objects.
