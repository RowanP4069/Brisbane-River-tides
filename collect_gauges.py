#!/usr/bin/env python3
"""Save recent measured water levels on the Brisbane River before they expire.

Sources keep only a short window, so this runs daily (GitHub Actions, see
.github/workflows/collect-gauges.yml) and merges what it fetches into monthly CSV
files on the gauge-data branch:

  bcc/YYYY-MM.csv      Brisbane City Council telemetry, 8 river gauges.
                       Metres AHD, 5-min slots with gaps. The source keeps 72 hours.
  msq_bar/YYYY-MM.csv  MSQ Brisbane Bar (Whyte Island) near real time.
                       Metres above LAT, 1-min, unvalidated. The source keeps about a week.

Each file has columns time_aest, gauge, value_m and is sorted by time, then gauge.
Readings are stored as received: no datum change, no cleaning. If a reading for the
same time and gauge arrives again with a different value, the newer value wins.

Usage:
  python collect_gauges.py --out DIR      # DIR is a checkout of the gauge-data branch

Uses only the standard library. Sources and licences: docs/data-sources.md.
"""
import argparse
import csv
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

AEST = timezone(timedelta(hours=10))      # Brisbane: UTC+10, no daylight saving
USER_AGENT = "Brisbane-River-tides gauge collector (github.com/RowanP4069/Brisbane-River-tides)"

# Council sensors on the Brisbane River itself, downstream to upstream.
BCC_GAUGES = {
    "E1594": "Mouth of Breakfast Ck, Newstead",
    "E1857": "Hawthorne AL",
    "E6749": "Brisbane City Gauge AL",
    "E1855": "Port Office Gauge",
    "E1856": "St Lucia AL",
    "E1588": "Mouth of Oxley Ck, Graceville",
    "E1765": "Jindalee (BCC) AL",
    "E1764": "Moggill (BCC) AL",
}
BCC_URL = ("https://data.brisbane.qld.gov.au/api/explore/v2.1/catalog/datasets/"
           "telemetry-sensors-rainfall-and-stream-heights-observations/exports/json")
MSQ_BAR_URL = "https://opendata.tmr.qld.gov.au/Whyte_Island.txt"
MSQ_BAR_GAUGE = "046046A"                 # MSQ station number for Brisbane Bar

FIELDS = ["time_aest", "gauge", "value_m"]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8-sig")


def fmt(t):
    """Naive AEST timestamp as text, minute resolution."""
    return t.strftime("%Y-%m-%d %H:%M")


def fetch_bcc():
    """Council river gauges: list of (time_aest, gauge, value) with empty slots dropped."""
    ids = ", ".join(f'"{g}"' for g in BCC_GAUGES)
    query = urllib.parse.urlencode({
        "where": f"gauge in ({ids}) and value is not null",
        "select": "measured, gauge, value",
    })
    rows = json.loads(fetch(f"{BCC_URL}?{query}"))
    out = []
    for r in rows:
        # "measured" is ISO with a UTC offset; convert to AEST.
        t = datetime.fromisoformat(r["measured"]).astimezone(AEST)
        out.append((fmt(t), r["gauge"], f'{r["value"]:.3f}'))
    return out


def fetch_msq_bar():
    """MSQ Brisbane Bar near real time: list of (time_aest, gauge, value).

    The file has a few header lines, then "ddmmyyyyHHMM  value" per minute, in AEST.
    """
    out = []
    for line in fetch(MSQ_BAR_URL).splitlines():
        parts = line.split()
        if len(parts) != 2 or len(parts[0]) != 12 or not parts[0].isdigit():
            continue                      # header lines
        t = datetime.strptime(parts[0], "%d%m%Y%H%M")
        out.append((fmt(t), MSQ_BAR_GAUGE, f"{float(parts[1]):.3f}"))
    return out


def merge(folder, rows):
    """Merge rows into folder/YYYY-MM.csv files. Returns the number of new or changed rows."""
    folder.mkdir(parents=True, exist_ok=True)
    by_month = {}
    for t, g, v in rows:
        by_month.setdefault(t[:7], {})[(t, g)] = v
    changed = 0
    for month, new in sorted(by_month.items()):
        path = folder / f"{month}.csv"
        old = {}
        if path.exists():
            with path.open(newline="") as f:
                old = {(r["time_aest"], r["gauge"]): r["value_m"] for r in csv.DictReader(f)}
        changed += sum(1 for k, v in new.items() if old.get(k) != v)
        old.update(new)
        with path.open("w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(FIELDS)
            for (t, g), v in sorted(old.items()):
                w.writerow([t, g, v])
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="folder to write into (gauge-data checkout)")
    args = ap.parse_args()
    out = Path(args.out)

    # Fetch each source separately, so one being down doesn't lose the other.
    failed = []
    for name, folder, fetcher in [("bcc", out / "bcc", fetch_bcc),
                                  ("msq_bar", out / "msq_bar", fetch_msq_bar)]:
        try:
            rows = fetcher()
        except Exception as e:            # network or format problem: report, carry on
            print(f"{name}: FAILED: {e}")
            failed.append(name)
            continue
        span = f"{min(r[0] for r in rows)} to {max(r[0] for r in rows)}" if rows else "no rows"
        print(f"{name}: {len(rows)} readings ({span} AEST), {merge(folder, rows)} new or changed")
    if failed:
        raise SystemExit(f"Failed: {', '.join(failed)}")   # non-zero exit: GitHub emails


if __name__ == "__main__":
    main()
