# Brisbane River tides

Interactive pages that show the **predicted tide** along the Brisbane River, from the Brisbane Bar to Kholo Creek, for any day in 2026 and 2027, alongside what the river actually did and what people on the water saw. It's a personal hobby project, made by a kayaker who wanted to see when the tide turns along different reaches of the river.

**Open the site: <https://rowanp4069.github.io/Brisbane-River-tides/>** It opens on today in Brisbane. Pick another day with the ◀ ▶ buttons or the calendar, and share a day with a link such as `…/Brisbane-River-tides/#2026-12-25`.

> **Predicted astronomical tide only. Not for navigation.**
> The model leaves out river flow, rain and dam releases, wind and storm surge. After rain the ebb can run for hours longer than shown, and the flood can disappear upriver altogether. The colours are proxies for flow direction worked out from predicted water level. They are not measured or modelled currents. Use Maritime Safety Queensland's official tide tables and local knowledge for planning.

![The page at 02:50 on 8 November 2026, coloured by rate of change: the tide is falling (blue) from Indooroopilly to Kholo Creek, while near the mouth it is close to turning (pale, with a hint of red at the Bar).](docs/screenshot.png)

## Contents

- [The pages](#the-pages)
- [Height predictions](#height-predictions)
  - [What it shows](#what-it-shows)
  - [How it works](#how-it-works)
  - [Limitations](#limitations)
- [Gauges (measured)](#gauges-measured)
- [Measured vs predicted](#measured-vs-predicted)
- [Report the flow](#report-the-flow)
  - [Results page](#results-page)
- [Guesswork: Kholo Creek to the weir ruin](#guesswork-kholo-creek-to-the-weir-ruin)
- [Run it locally](#run-it-locally)
- [Run your own copy (fork)](#run-your-own-copy-fork)
- [Data and attribution](#data-and-attribution)
- [Acknowledgements](#acknowledgements)
- [Licence](#licence)

## The pages

All the pages share a link bar at the top. The site is rebuilt every night and after each daily data collection.

| Page | Address | What it is |
|---|---|---|
| Height predictions | [index](https://rowanp4069.github.io/Brisbane-River-tides/) | The predicted tide along the river: 3D map and profile, any day in 2026 and 2027 |
| Gauges | [gauges.html](https://rowanp4069.github.io/Brisbane-River-tides/gauges.html) | Measured river levels from the last 24 to 72 hours |
| Measured vs predicted | [compare.html](https://rowanp4069.github.io/Brisbane-River-tides/compare.html) | How the saved readings compare with the predictions, for a period you choose |
| Report the flow | [report.html](https://rowanp4069.github.io/Brisbane-River-tides/report.html) | Report which way the water was moving (citizen science) |
| Report the flow (results) | [results.html](https://rowanp4069.github.io/Brisbane-River-tides/results.html) | Every report and field observation so far, by reach |
| Guesses | [guesswork.html](https://rowanp4069.github.io/Brisbane-River-tides/guesswork.html) | A sandbox carrying the model on above Kholo Creek with named guesses |

## Height predictions

### What it shows

- **3D map:** a bar every 500 m along the river. Bar height is the predicted water level, and the colour shows whether it's rising or falling (or the rate of change, or a surface-slope proxy).
- **Profile:** the same data along the river as a chart. A shaded band shows the range at each point over the whole 24 h or 48 h window: its top line (solid) is the highest level there, its bottom line (dashed) the lowest. Each point reaches its highest at a different time (the tide arrives later upstream), so the top line is not the river at any one moment.
- **Marked place:** tap or drag on the profile, click a bar on the map, or pick a tide station or boat ramp from the **Place** list. The place gets a purple line on the profile and a purple ring and label on the map, and a readout of its height now, whether it's rising or falling, and its highest and lowest in the window with their times. It snaps to the nearest 500 m point, and goes in the address too (e.g. `…/#2026-12-25/km2.5`) so a link opens on the same day and place.
- **Day:** ◀ ▶ for the previous or next day, a date box with a calendar, **Today**, and a 24 h or 48 h window. Changing day keeps the same time of day, and the day goes in the address so a link opens on it.
- **Time controls:** 10-minute steps through the window, with play/pause, speed, and arrow keys to step through it. **Now** jumps to the current time in Brisbane and pauses there; **−1 h** and **+1 h** step an hour at a time, carrying on into the next or previous day.

### How it works

Only the Brisbane Bar has a published 10-minute prediction. Upriver places are published as corrections relative to the Bar: a time lag and a height ratio (Maritime Safety Queensland's *Semidiurnal Tidal Planes*). For each point along the river, the script takes the Bar prediction, delays it by that point's lag, scales it by its ratio, and adds the local mean sea level:

    height(x, t) = MSL(x) + ratio(x) × (Bar(t − lag(x)) − MSL_Bar)

Lag, ratio and MSL are interpolated along the river between the published places. Distances are measured along the river centreline, built from Queensland watercourse data.

Python is the source of truth: `river_tides.py` works out everything about places (the points, and each one's lag, ratio and MSL) and puts them in the page with the whole Bar series. The page computes each day's heights itself with the same one-line formula, so it can show any day without a rebuild. `check_parity.py` checks that the two agree (see [Run it locally](#run-it-locally)).

### Limitations

The main ones are below. `data/README.md` covers them in full, along with the data sources and how each file was made.

- Heights at each place are above that place's own lowest astronomical tide (LAT), so they can't be compared as one water surface.
- One lag and one ratio per place. The real tide upriver has a shorter, steeper flood and a longer ebb, which this method can't reproduce.
- From Seventeen Mile Rocks upstream there are no published ratios, so the model uses an estimate. On big spring tides, heights there can dip below LAT.
- Between Indooroopilly and Seventeen Mile Rocks the published low-water lag decreases going upstream, so the tide appears to arrive earlier further up. This is in the published tables (the same in 2025 and 2026), and the page marks it.

## Gauges (measured)

The **Gauges** page shows what the river actually did: the last 24, 48 or 72 hours of readings from Brisbane City Council's eight Brisbane River gauges, from Breakfast Creek to Moggill, and the Bureau of Meteorology's Colleges Crossing gauge (540063, km 83.8, above Kholo Creek).

- The page fetches the council's readings **live** from its open data service when it opens (⟳ Refresh fetches again). Nothing is forecast.
- Heights are **metres AHD**, one datum for every gauge, so unlike the predictions they form a real water surface. The predictions use each place's LAT, about 1.2 m lower at Port Office.
- Readings arrive at irregular times. Gaps of up to an hour are bridged with a straight line; longer gaps, and gauges whose latest readings haven't arrived yet, show as *no reading*.
- Rising, falling or near slack comes from a straight line fitted to the readings within 45 minutes either side (slack below 3 cm/h), because readings wobble by a centimetre or more near high and low water. A level with too few readings around it to tell its direction shows as *direction unknown*.
- **Colleges Crossing** comes from the project's own copy of BoM's readings on the `gauge-data` branch (`bom/`, collected every 15 minutes, and `bom-filled/`, filled by hand from BoM's table), so it can lag a little; the page says when its latest reading is over an hour old. It reports only each 0.05 m change, so its last level is held for up to 3 hours. It reads nothing below 0.59 m AHD, shown as *at gauge floor* (0.59 m or lower). One-off telemetry glitches are left out, by the same rule as `compare_gauges.py`.
- `build_gauges.py` builds it. `data/gauges.csv` holds each gauge's position along the river; `build_gauges.py --download` remakes it from the council's gauge list.

## Measured vs predicted

The **Measured vs predicted** page compares what the river did with the predictions, for any period there are readings for.

**The saved readings.** The sources keep readings only briefly (the council 72 hours, the MSQ Bar feed about a week, the storm tide feed 7 days), so `collect_gauges.py` saves them before they go, to the [`gauge-data` branch](https://github.com/RowanP4069/Brisbane-River-tides/tree/gauge-data):

- daily (GitHub Action `collect-gauges.yml`, about 03:00 AEST): the eight council gauges, the MSQ Brisbane Bar gauge, and 11 Queensland Government storm tide gauges around Moreton Bay, Pumicestone Passage and the Broadwater, with their official predictions (for future Moreton Bay work);
- every 15 minutes: BoM river heights for the Brisbane River gauges the council doesn't have, including Colleges Crossing (540063) and Kholo Bridge (540256). BoM's bulletin holds only each gauge's latest reading, so gaps from late runs are filled by hand from BoM's web table (`bom-filled/`). GitHub's 15-minute schedule (`collect-bom.yml`) didn't fire reliably, so for this site the same command runs on a schedule outside GitHub.

`docs/data-sources.md` describes the sources.

**The comparison.** `compare_gauges.py` reads the saved readings: run `git fetch origin gauge-data`, then `python compare_gauges.py` (optionally `--since` / `--until`). For each gauge it reports the datum offset (council gauges read AHD, the model LAT), how far the measured level strays from the prediction, and how early or late each high and low water came, with high and low water reported separately. The fitting is done once in Python; the page only averages over the period you choose. The script's description lists the method's known limits. Two things the council data does: a gauge only reports when the level moves a step (1 to 5 cm), and the Jindalee and Moggill gauges seem unable to read low water.

Colleges Crossing is on the page too, above Kholo Creek where there are no predictions, so it is compared with the [Guesswork](#guesswork-kholo-creek-to-the-weir-ruin) page's guesses and labelled as such: its timing tests G-lag, and its fitted "LAT below AHD" sits beside G-datum. BoM's series has one-off telemetry glitches (a single reading 0.40 or 0.80 m out, often in the same minute as a real one); `compare_gauges.py` drops those, but not freshwater after rain, which raises the whole level for hours or days and shows in the residuals.

BoM's Goodna gauge (540670, km 62.3) is compared with the model like the council gauges. It reads metres on its own local gauge height, and BoM doesn't publish where that gauge's zero is, so its fitted offset is LAT below the gauge's zero rather than below AHD; timing, range and residuals don't depend on it. Its position (km 62.3) is from BoM's index of Queensland river height stations (*Queensland Flood Warning Networks*, Section 3). It has only the 15-minute collection behind it, so fewer of its tides are timed.

## Report the flow

The **Report the flow** page lets people on the river report which way the water was moving, how strongly, and how the water looked. Reports are taken from the mouth up to the old weir ruin below Mt Crosby (km 87.4), where the tide stops. When a report is sent below Kholo Creek, the page compares it with the model at that place and time (rising level: water coming in; falling: going out; within 45 minutes of high or low water: turning) and says whether it matches. A mismatch is useful data: the current turns later than the level, and freshwater flow pushes it downstream.

- `build_report.py` builds the page. Reports go to a Google Form owned by the project. Its sheet publishes only the time and the public part of each report: the place as km up the river and which bank, never the exact position, and not the notes.
- `collect_reports.py` checks the published reports once a day (time, place, values; exact repeats dropped) and rewrites the [`reports` branch](https://github.com/RowanP4069/Brisbane-River-tides/tree/reports), whose README describes the columns. Reports are published at that daily run, never live. The page's map and list show the last 30 days.
- The map shows public boat ramps (`data/ramps.csv`, from Brisbane City Council and MSQ's Beacon to Beacon guide) as places to find; tapping one sets the report's place.
- Above Kholo Creek, where the tide tables stop, reports are recorded without a verdict.
- The page remembers the reporter's name in the browser (local storage, not a cookie) and gives each device a random ID. Reports publish its first 8 characters as `device`, so reports from one device can be grouped; the private part keeps the whole ID. Nothing about the person or their IP address is stored.
- To hide a report, add its `submitted_aest` to `data/reports_hidden.csv`; to hide every report from a device, fill in the `device` column instead. They disappear at the next daily run.
- [docs/report-form-setup.md](docs/report-form-setup.md) says how the Google Form and its sheet are set up, to check or rebuild them.
- Reports are shared under CC BY 4.0.

### Results page

**Report the flow (results)** gathers everything seen so far: every accepted report and the project's own field observations (`data/observations.csv`), on a map with two confidence lines (Indooroopilly, where MSQ's published ratios end, and Kholo Creek, where MSQ's figures end), a summary by reach, and a chart of where along the river and how long before or after high water at the Bar each was seen.

- `build_results.py` builds it, working each report's verdict out again against the current model, so the match rate follows the model as it improves. The build prints any report whose verdict differs from the one the reporter was shown.
- A reach's match rate shows as "m of n" until it has 5 checkable reports, then as a percentage. Reports from one device are counted as one device, so a single keen paddler doesn't look like many confirmations.
- Above Kholo Creek the page shows the hypotheses under test (`docs/hypotheses.md`) with their running tallies.

## Guesswork: Kholo Creek to the weir ruin

A **sandbox**, not predictions (the "Guesses" link on every page; kept out of search engines). It is the predictions page with the same model to Kholo Creek, carried on to the old weir ruin (km 87.4) with **guesses**, each named and dated in `data/guesses.csv`: G-lag and G-ratio (held at Kholo Creek's values), G-datum (Kholo Creek's LAT in m AHD, so heights can be read against the gauge and level marks) and G-floor (the crests of the gravel runs: above a run the water can't fall below its crest, and the bar shows it "running fresh"). Guess bars are pale and hatched; the project's own field observations are dark markers, with a list under the profile.

- `river_tides.py --sandbox` builds it.
- Under the profile, a **tidal-head chart** shows everything seen above km 75 (flow reports and our observations) against the predicted Kholo Creek level at the time, with the gravel runs as lines and the guessed crests as ticks. It contains no guesses itself: it is the evidence the G-floor guesses can be checked against.
- A guess tuned on a day's data can't count as a test on that day (`not_a_test_on`). Changing a guess means a new date on its row; git keeps the old value.
- Guesses are not hypotheses. Claims tested against data set in advance stay in `docs/hypotheses.md`, and only they can ever reach the Height predictions page.

## Run it locally

Needs Python 3 (developed on 3.14). From the project folder:

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python river_tides.py --start 2026-11-08

You only need this to make pages for other dates or settings, or to work on the code; the hosted site is built the same way (see `.github/workflows/pages.yml`). Each script writes to `output/`, with the same file names as the website so the links between pages work. Open the files in a web browser. The pages need an internet connection for the map libraries and tiles, and the 3D map needs WebGL (without it, the profile and controls still work).

| Page | Command | Writes |
|---|---|---|
| Height predictions | `river_tides.py` | `output/index.html` |
| Guesses | `river_tides.py --sandbox` | `output/guesswork.html` |
| Gauges | `build_gauges.py` | `output/gauges.html` |
| Measured vs predicted | `compare_gauges.py` | `output/compare.html` |
| Report the flow | `build_report.py` | `output/report.html` |
| Report the flow (results) | `build_results.py` | `output/results.html` |

Measured vs predicted reads the `gauge-data` branch, and the two Report the flow pages read the `reports` branch, so run `git fetch origin gauge-data reports` first.

Useful `river_tides.py` options (`--help` lists them all; each script has its own `--help`):

- `--start 2026-11-08T06:00`: the day the page opens on, and the time of day each window starts (local AEST). Without it, the page opens on the viewer's today.
- `--hours 12`: window length (default 48). The page offers 24 h and 48 h, plus this if different.
- `--csv FILE ...`: different Brisbane Bar prediction file(s). By default it uses every `data/bar_YYYY_10min.csv`; 2026 and 2027 are committed. `fetch_bar.py --year YYYY` fetches another year.
- `--json FILE`: also save the page data as JSON.
- `--stamp`: show when the page was built (AEST). The hosted site uses it; it's off by default so repeat runs give identical files.

Other tools:

- `check_parity.py` checks that the page and Python agree to within the 1 mm rounding, over a set of test days; run it after changing the model on either side (it needs Node.js). It also checks that the Measured vs predicted page's statistics match `compare_gauges.py`. The site build stops if it fails.
- `build_centreline.py` rebuilds `data/centreline.csv` from the saved watercourse data. You only need it if that data or the station positions change.
- `fetch_bar.py --year YYYY` fetches a year of Brisbane Bar predictions from data.qld.gov.au.

## Run your own copy (fork)

Everything the site needs is in this repository and its two data branches; no keys or secrets are used. A fork needs these steps:

1. **Copy all the branches.** When forking, untick "Copy the `main` branch only". The site build fetches the `gauge-data` and `reports` branches and stops if they are missing.
2. **Turn on Actions.** Forks start with workflows, and their schedules, turned off. Turn them on from the Actions tab. GitHub also turns off schedules in a public repository after 60 days with no activity.
3. **Turn on Pages.** Settings → Pages → Source: GitHub Actions.
4. **Use your own report form, or none.** `FORM` in `build_report.py` and `PUBLIC_CSV` in `collect_reports.py` point at this project's Google Form and sheet. Left as they are, reports sent from your copy's page land in this project's sheet. Either make your own form and sheet ([docs/report-form-setup.md](docs/report-form-setup.md)) and put in their addresses, or set the form's `action` to `""`: the page still works and gives its verdict, but says the report wasn't sent.
5. **Point the remaining addresses at your copy.** `BOM_FILES` in `build_gauges.py` reads Colleges Crossing from this repository's `gauge-data` branch, and `web/results_template.html` links to this repository's `docs/hypotheses.md`.
6. **Expect gaps in the BoM readings.** `collect-bom.yml` asks for a run every 15 minutes, but GitHub delays and skips frequent scheduled runs. For the hosted site, the same `collect_gauges.py --sources bom` command runs on a schedule outside GitHub.
7. **Add each new year's Bar predictions** with `fetch_bar.py`. The committed files end on 31 December 2027, and the predictions page needs the next year before then.

The data branches carry this project's readings and reports. Keep the attribution below if you publish them.

## Data and attribution

Source data and its licences (details for each file in `data/README.md`, and for the measured sources in `docs/data-sources.md`):

- **Maritime Safety Queensland** (© State of Queensland, Department of Transport and Main Roads), CC BY 4.0: Brisbane Bar predicted tides, the *Semidiurnal Tidal Planes*, Brisbane Bar gauge readings, and three boat ramp positions from the *Beacon to Beacon Guide: Brisbane River and Bremer River*.
- **Queensland Department of Resources** (© State of Queensland), CC BY 4.0: Watercourse lines – Queensland.
- **Queensland Government Coastal Data System**, CC BY 4.0: storm tide gauge readings and predictions.
- **Brisbane City Council**, CC BY 4.0: river gauge readings and the gauge list, and boat ramp locations.
- **Bureau of Meteorology**: river heights, used under the CC BY terms stated on its bulletins.
- **OpenStreetMap** (© OpenStreetMap contributors, ODbL): positions of the Colleges Crossing bridge, the pipe crossing, the weir ruin and the power lines in `data/features.csv`.
- **Flow reports** from the Report the flow page are shared under CC BY 4.0.

Basemap: [OpenFreeMap](https://openfreemap.org), © OpenMapTiles, data from OpenStreetMap. The map shows this attribution itself.

## Acknowledgements

Built with help from Claude (Anthropic), using Claude Code.

## Licence

The code (the Python scripts in the top folder, `web/` and the GitHub workflows in `.github/workflows/`) is under the MIT licence; see [LICENSE](LICENSE). The files in `data/` keep their original licences, as listed above.
