#!/usr/bin/env python3
"""Fetch a year of Brisbane Bar 10-minute tide predictions from data.qld.gov.au.

Writes data/bar_YYYY_10min.csv in the same format as the downloadable CSV
(UTF-8 with BOM; columns _id, Date, Time, Ind, Reading), so river_tides.py reads
it like any other year. The file is then committed: page builds use the copy in
data/ and never depend on the API being up.

Why the API and not the download link: the 2027 download link returned a web page
instead of the file (checked 2026-11-08), while the API worked.

The API's 2027 table holds identical duplicate rows (14 Aug to 31 Dec loaded
twice). Exact duplicates are dropped; two *different* readings for the same time
stop the script, as do gaps. Rows are written in time order and _id is renumbered
from 1, as in the published files.

Usage:
  python fetch_bar.py --year 2027
  python fetch_bar.py --year 2026 --out /tmp/check.csv     # compare with data/

Uses only the standard library. Source and licence: data/README.md.
"""
import argparse
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

API = "https://www.data.qld.gov.au/api/3/action"
DATASET = "brisbane-bar-tide-gauge-predicted-interval-data"
USER_AGENT = "Brisbane-River-tides (github.com/RowanP4069/Brisbane-River-tides)"
PAGE = 32000                                 # rows per API request (the API's maximum)
HERE = Path(__file__).parent


def api(action, **params):
    url = f"{API}/{action}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.load(resp)
    if not body.get("success"):
        raise SystemExit(f"API error from {action}: {body.get('error')}")
    return body["result"]


def find_resource(year):
    """Resource id of the year's CSV in the dataset, matched on the resource name.

    Uses package_search: on 2026-11-08 package_show did not yet list the 2027
    resource, while the search index did.
    """
    found = api("package_search", fq=f"name:{DATASET}", rows=1)["results"]
    if not found:
        raise SystemExit(f"Dataset {DATASET} not found")
    matches = [r for r in found[0]["resources"]
               if r["name"].strip().startswith(str(year)) and r.get("datastore_active")]
    if len(matches) != 1:
        names = [r["name"] for r in found[0]["resources"]]
        raise SystemExit(f"Expected one queryable {year} resource, found {len(matches)}. "
                         f"Resources: {names}")
    return matches[0]["id"]


def fetch_rows(resource_id):
    """All rows of a datastore table, as dicts (values are text)."""
    rows, offset = [], 0
    while True:
        res = api("datastore_search", resource_id=resource_id, limit=PAGE, offset=offset,
                  sort="_id")
        rows += res["records"]
        offset += len(res["records"])
        if not res["records"] or offset >= res["total"]:
            return rows


def clean(rows, year):
    """Drop exact duplicates; check one reading per 10-minute step for the whole year.

    Returns (time, row) pairs in time order.
    """
    by_time = {}
    for r in rows:
        t = datetime.strptime(f'{r["Date"].strip()} {r["Time"].strip()}', "%d/%m/%Y %H:%M")
        key = (r["Ind"].strip(), r["Reading"].strip())
        if t in by_time and by_time[t][0] != key:
            raise SystemExit(f"Two different readings for {t}: {by_time[t][0]} and {key}")
        by_time[t] = (key, r)
    times = sorted(by_time)
    start, end = datetime(year, 1, 1), datetime(year, 12, 31, 23, 50)
    expected = int((end - start) / timedelta(minutes=10)) + 1
    if times[0] != start or times[-1] != end or len(times) != expected:
        raise SystemExit(f"Expected {expected} readings from {start} to {end}; "
                         f"got {len(times)} from {times[0]} to {times[-1]}")
    print(f"{len(rows)} rows from the API, {len(rows) - len(times)} exact duplicates dropped, "
          f"{len(times)} readings {start:%Y-%m-%d} to {end:%Y-%m-%d}, every 10 min")
    return [(t, by_time[t][1]) for t in times]


def write_csv(pairs, path):
    """Same layout as the published CSV, byte for byte: BOM, a header ending in CRLF
    (a quirk of MSQ's files), data rows ending in LF, values as given."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="\n") as f:
        f.write("_id,Date,Time,Ind,Reading\r\n")
        for i, (t, r) in enumerate(pairs, start=1):
            f.write(f'{i},{t:%d/%m/%Y},{t:%H:%M},{r["Ind"].strip()},{r["Reading"].strip()}\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--year", type=int, required=True, help="prediction year, e.g. 2027")
    ap.add_argument("--resource", help="datastore resource id (default: looked up by year)")
    ap.add_argument("--out", help="file to write (default: data/bar_YEAR_10min.csv)")
    args = ap.parse_args()

    resource = args.resource or find_resource(args.year)
    print(f"{args.year}: resource {resource}")
    pairs = clean(fetch_rows(resource), args.year)
    out = Path(args.out) if args.out else HERE / "data" / f"bar_{args.year}_10min.csv"
    write_csv(pairs, out)
    print("Wrote", out)


if __name__ == "__main__":
    main()
