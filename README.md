# Flow reports: Brisbane River (reports branch)

This branch holds **data only**: reports of which way the Brisbane River was flowing, sent by people on the river from the [Report the flow](https://rowanp4069.github.io/Brisbane-River-tides/report.html) page. `collect_reports.py` (on `main`) rewrites it once a day from the reports received so far, leaving out any that fail its checks or that were hidden by hand (`data/reports_hidden.csv` on `main`).

## Files

`reports/YYYY-MM.csv`, by the month of the report. Columns:

| column | meaning |
|---|---|
| submitted_aest | when the report was sent (AEST) |
| time_aest | when the flow was seen (AEST), as the reporter gave it |
| km | distance up the river from the Brisbane Bar, along the centreline, to 0.1 km |
| bank | `left` or `right` bank looking downstream, or `mid` (within 30 m of the centreline) |
| alias | the name the reporter chose to show (blank = anonymous) |
| dir_kind | `river` (directions are relative to the river) |
| dir | `up` (inland), `down` (to the sea), `slack`, or `swirl` (swirling / can't tell) |
| strength | 0 slack, 1 gentle, 2 moderate, 3 strong, 4 very strong (blank when swirling) |
| speed_kmh | the reporter's speed estimate, if given |
| clarity | 1 very muddy to 5 clear, if given |
| problems | `;`-separated: debris, rubbish, foam, oil, algae, smell, dead_fish |
| verdict | what the page told the reporter: `match`, `turn` (near high/low water), `mismatch`, `none` |

Exact positions and notes are not published.

## Licence

Reports are shared by their reporters under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Credit "Brisbane River flow reports, github.com/RowanP4069/Brisbane-River-tides".

Not for navigation.
