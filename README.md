# Brisbane River tides

An interactive page that shows the **predicted tide** along the Brisbane River, from the Brisbane Bar to Kholo Creek, over a day. It's a personal hobby project, made by a kayaker who wanted to see when the tide turns along different reaches of the river.

> **Predicted astronomical tide only. Not for navigation.**
> The model leaves out river flow, rain and dam releases, wind and storm surge. After rain the ebb can run for hours longer than shown, and the flood can disappear upriver altogether. The colours are proxies for flow direction worked out from predicted water level. They are not measured or modelled currents. Use Maritime Safety Queensland's official tide tables and local knowledge for planning.

## What it shows

- **3D map:** a bar every 500 m along the river. Bar height is the predicted water level, and the colour shows whether it's rising or falling (or the rate of change, or a surface-slope proxy).
- **Profile:** the same data along the river as a chart, with the day's high-to-low range at each point.
- **Time controls:** a 24-hour window at 10-minute steps, with play/pause, speed, and arrow keys to step through it.

## How it works

Only the Brisbane Bar has a published 10-minute prediction. Upriver places are published as corrections relative to the Bar: a time lag and a height ratio (Maritime Safety Queensland's *Semidiurnal Tidal Planes*). For each point along the river, the script takes the Bar prediction, delays it by that point's lag, scales it by its ratio, and adds the local mean sea level:

    height(x, t) = MSL(x) + ratio(x) × (Bar(t − lag(x)) − MSL_Bar)

Lag, ratio and MSL are interpolated along the river between the published places. Distances are measured along the river centreline, built from Queensland watercourse data.

## Run it

Needs Python 3 (developed on 3.14). From the project folder:

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python river_tides.py --start 2026-11-08

This writes `output/river_tides.html`. Open it in a web browser. The page needs an internet connection for the map libraries and tiles, and the 3D map needs WebGL (without it, the profile and controls still work).

Useful options (`--help` lists them all):

- `--start 2026-11-08T06:00`: start of the window, local AEST.
- `--hours 12`: window length (default 24).
- `--csv FILE`: a different Brisbane Bar prediction file. The committed file covers 2026 only.
- `--json FILE`: also save the page data as JSON.

`build_centreline.py` rebuilds `data/centreline.csv` from the saved watercourse data. You only need it if that data or the station positions change.

## Limitations

The main ones are below. `data/README.md` covers them in full, along with the data sources and how each file was made.

- Heights at each place are above that place's own lowest astronomical tide (LAT), so they can't be compared as one water surface.
- One lag and one ratio per place. The real tide upriver has a shorter, steeper flood and a longer ebb, which this method can't reproduce.
- From Seventeen Mile Rocks upstream there are no published ratios, so the model uses an estimate. On big spring tides, heights there can dip below LAT.
- Between Indooroopilly and Seventeen Mile Rocks the published low-water lag decreases going upstream, so the tide appears to arrive earlier further up. This is in the published tables (the same in 2025 and 2026), and the page marks it.

## Data and attribution

All source data is © State of Queensland and licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/):

- Brisbane Bar predicted tides and the Semidiurnal Tidal Planes: Maritime Safety Queensland (Department of Transport and Main Roads).
- Watercourse lines – Queensland: Department of Resources.

Basemap: [OpenFreeMap](https://openfreemap.org), © OpenMapTiles, data from OpenStreetMap. The map shows this attribution itself.

## Acknowledgements

Built with help from Claude (Anthropic), using Claude Code.

## Licence

The code (`river_tides.py`, `build_centreline.py` and `web/`) is under the MIT licence; see [LICENSE](LICENSE). The files in `data/` keep their original CC BY 4.0 licences, as listed above.
