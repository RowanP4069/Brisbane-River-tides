#!/usr/bin/env python3
"""Save recent measured water levels on the Brisbane River before they expire.

Sources keep only a short window, so this runs daily (GitHub Actions, see
.github/workflows/collect-gauges.yml) and merges what it fetches into monthly CSV
files on the gauge-data branch:

  bcc/YYYY-MM.csv      Brisbane City Council telemetry, 8 river gauges.
                       Metres AHD, 5-min slots with gaps. The source keeps 72 hours.
  msq_bar/YYYY-MM.csv  MSQ Brisbane Bar (Whyte Island) near real time.
                       Metres above LAT, 1-min, unvalidated. The source keeps about a week.
  cds/YYYY-MM.csv      Queensland Government storm tide gauges (Coastal Data System),
                       the Bar and 11 sites around Moreton Bay, Pumicestone Passage and
                       the Broadwater (for roadmap item 15). Metres above LAT, 10-min.
                       The source keeps 7 days. Also stores the official prediction.
  bom/YYYY-MM.csv      Bureau of Meteorology river heights for the Brisbane River gauges
                       (station names starting "Brisbane River at", e.g. 540063 Colleges
                       Crossing, 540256 Kholo Bridge), from the Brisbane basin river height
                       bulletin IDQ60286 on BoM's public anonymous FTP. The bulletin holds
                       only each gauge's LATEST reading, so this source is also run every
                       15 min (.github/workflows/collect-bom.yml). Metres, on the datum the
                       bulletin gives (AHD, or LGH = local gauge height; 540063's gauge zero
                       is 0 m AHD). bom/stations.csv lists the gauges' names and datums.

Files have columns time_aest, gauge, value_m (cds/ adds prediction_m, bom/ adds datum)
and are sorted
by time, then gauge.
Readings are stored as received: no datum change, no cleaning. If a reading for the
same time and gauge arrives again with a different value, the newer value wins.

Usage:
  python collect_gauges.py --out DIR      # DIR is a checkout of the gauge-data branch
  python collect_gauges.py --out DIR --sources bom   # only some sources

Uses only the standard library. Sources and licences: docs/data-sources.md.
"""
import argparse
import csv
import html
import json
import re
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

# Coastal Data System 7-day feed (data.qld.gov.au, "Coastal Data System - Near real time
# storm tide data"). Its sister feed stdtide-7dayopdata.csv has the same values for a
# subset of sites (checked 2026-11-09), so only this one is fetched.
CDS_URL = "https://apps.des.qld.gov.au/data-sets/storm-tides/tide-7dayopdata.csv"
CDS_MISSING = "-99.000"                   # the feed's marker for no reading (yet)
# Site codes as in the feed, roughly north to south.
CDS_SITES = {
    "goldenbeach": "Golden Beach (Pumicestone Passage)",
    "hallsbay": "Halls Bay (Pumicestone Passage)",
    "donnybrook": "Donnybrook (Pumicestone Passage)",
    "scarborough": "Scarborough (Moreton Bay)",
    "tangalooma": "Tangalooma (Moreton Bay)",
    "shorncliffe": "Shorncliffe (Moreton Bay)",
    "whyteislandnx": "Brisbane Bar (Whyte Island)",
    "birkdale": "Birkdale (Moreton Bay)",
    "rabybay": "Raby Bay (Moreton Bay)",
    "bananabank": "Banana Bank (Moreton Bay)",
    "coombabahst": "Coombabah (Broadwater)",
    "goldcoast": "Gold Coast Seaway (Southport)",
}

# BoM's anonymous FTP is the route BoM provides for automated access to current
# products (its README: ftp://ftp.bom.gov.au/anon/gen/README). The web pages
# (bom.gov.au) refuse scripts, so they are never fetched here.
BOM_URL = "ftp://ftp.bom.gov.au/anon/gen/fwo/IDQ60286.html"
BOM_PREFIX = "Brisbane River at "

FIELDS = ["time_aest", "gauge", "value_m"]
CDS_FIELDS = FIELDS + ["prediction_m"]
BOM_FIELDS = FIELDS + ["datum"]


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


def fetch_cds():
    """Storm tide gauges: list of (time_aest, gauge, value, prediction) for CDS_SITES.

    The file has a "provided @" line and a header, then one row per site per 10 min:
    Site, Seconds, DateTime, Water Level, Prediction, Residual, Latitude, Longitude.
    DateTime is AEST. Residual is always Water Level - Prediction, so it isn't kept.
    Slots with no reading yet (-99) are skipped; a later run fills them in.
    """
    out = []
    for r in csv.reader(fetch(CDS_URL).splitlines()[2:]):
        if len(r) < 5 or r[0] not in CDS_SITES or r[3].strip() == CDS_MISSING:
            continue
        t = datetime.strptime(r[2].strip(), "%Y-%m-%dT%H:%M")
        out.append((fmt(t), r[0], f"{float(r[3]):.3f}", f"{float(r[4]):.3f}"))
    return out


def bom_reading_time(text, issued):
    """'02.14PM Tue' -> naive AEST datetime: the latest such time at or before the
    bulletin's issue time. None if that would be more than 6 days back (too stale to
    place the weekday with certainty)."""
    clock, weekday = text.split()
    t = datetime.strptime(clock, "%I.%M%p")
    for back in range(7):
        day = issued.date() - timedelta(days=back)
        if day.strftime("%a") == weekday:
            when = datetime.combine(day, t.time())
            # A minute or two of slack: the reading can be stamped just after issue.
            return when if when <= issued + timedelta(minutes=5) else None
    return None


def parse_bom(page):
    """Rows (time_aest, gauge, value, datum) and {gauge: (name, datum)} from IDQ60286.

    Table rows have 9 cells: name, type, time/day, height, datum, tendency, crossing,
    flood class, links. The station number comes from the "Table" link
    (IDQ65389.<station>.tbl.shtml). Rows with no current reading are skipped.
    """
    m = re.search(r"Issued at\s+(\d\d:\d\d [AP]M) AEST \w+ (\d+ \w+ \d{4})", page)
    if not m:
        raise ValueError("no 'Issued at' time in the bulletin")
    issued = datetime.strptime(f"{m.group(2)} {m.group(1)}", "%d %B %Y %I:%M %p")
    rows, stations = [], {}
    for tr in re.findall(r"<tr>(.*?)</tr>", page, re.S):
        cells = [html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c))).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        sid = re.search(r"IDQ65389\.(\w+)\.tbl", tr)
        if len(cells) != 9 or not sid or not cells[0].startswith(BOM_PREFIX):
            continue
        name, _, when, height, datum = cells[:5]
        stations[sid.group(1)] = (name[len(BOM_PREFIX):], datum)
        if not when or not height:
            continue                      # manual gauge, or no reading at present
        t = bom_reading_time(when, issued)
        if t is not None:
            rows.append((fmt(t), sid.group(1), f"{float(height):.3f}", datum))
    if not stations:
        raise ValueError("no Brisbane River gauges found: has the bulletin's layout changed?")
    return rows, stations


def fetch_bom():
    """BoM Brisbane basin bulletin over FTP. Returns (rows, stations); see parse_bom."""
    with urllib.request.urlopen(BOM_URL, timeout=120) as resp:
        return parse_bom(resp.read().decode("latin-1"))


def write_bom_stations(folder, stations):
    """bom/stations.csv: every Brisbane River gauge seen in the bulletin, merged with
    any listed before (a gauge can drop out of the bulletin for a while)."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "stations.csv"
    old = {}
    if path.exists():
        with path.open(newline="") as f:
            old = {r["gauge"]: (r["name"], r["datum"]) for r in csv.DictReader(f)}
    old.update(stations)
    with path.open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["gauge", "name", "datum"])
        for g, (n, d) in sorted(old.items()):
            w.writerow([g, n, d])


def merge(folder, rows, fields=FIELDS):
    """Merge rows into folder/YYYY-MM.csv files. Returns the number of new or changed rows.

    Each row is (time_aest, gauge, *values), matching fields.
    """
    folder.mkdir(parents=True, exist_ok=True)
    by_month = {}
    for t, g, *v in rows:
        by_month.setdefault(t[:7], {})[(t, g)] = v
    changed = 0
    for month, new in sorted(by_month.items()):
        path = folder / f"{month}.csv"
        old = {}
        if path.exists():
            with path.open(newline="") as f:
                old = {(r["time_aest"], r["gauge"]): [r[k] for k in fields[2:]]
                       for r in csv.DictReader(f)}
        changed += sum(1 for k, v in new.items() if old.get(k) != v)
        old.update(new)
        with path.open("w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(fields)
            for (t, g), v in sorted(old.items()):
                w.writerow([t, g, *v])
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sources = ["bcc", "msq_bar", "cds", "bom"]
    ap.add_argument("--out", required=True, help="folder to write into (gauge-data checkout)")
    ap.add_argument("--sources", nargs="+", choices=sources, default=sources,
                    help="which sources to fetch (default: all)")
    args = ap.parse_args()
    out = Path(args.out)

    def bom():
        rows, stations = fetch_bom()
        write_bom_stations(out / "bom", stations)
        return rows

    # Fetch each source separately, so one being down doesn't lose the other.
    failed = []
    for name, fetcher, fields in [("bcc", fetch_bcc, FIELDS),
                                  ("msq_bar", fetch_msq_bar, FIELDS),
                                  ("cds", fetch_cds, CDS_FIELDS),
                                  ("bom", bom, BOM_FIELDS)]:
        if name not in args.sources:
            continue
        try:
            rows = fetcher()
        except Exception as e:            # network or format problem: report, carry on
            print(f"{name}: FAILED: {e}")
            failed.append(name)
            continue
        span = f"{min(r[0] for r in rows)} to {max(r[0] for r in rows)}" if rows else "no rows"
        print(f"{name}: {len(rows)} readings ({span} AEST), {merge(out / name, rows, fields)} new or changed")
    if failed:
        raise SystemExit(f"Failed: {', '.join(failed)}")   # non-zero exit: GitHub emails


if __name__ == "__main__":
    main()
