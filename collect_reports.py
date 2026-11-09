#!/usr/bin/env python3
"""Copy accepted flow reports from the Google Form's published sheet to the reports branch.

The "Report the flow" page (build_report.py) sends each report to a Google Form. The
form's sheet has a "public" tab with just the submission time and the published part
of each report (JSON), and only that tab is published, as CSV (PUBLIC_CSV). Exact
positions and notes stay in the sheet's other tab, which is not published.

This script reads the whole public tab, checks every report, adds the accepted ones to
those already in reports/YYYY-MM.csv (by report time) in the folder given, a checkout
of the reports branch, drops any hidden by hand (data/reports_hidden.csv), and rewrites
the files. Reports already saved are kept even if the fetch doesn't include them:
Google's published copy can lag by 10 minutes or more and differs by location (on
2026-11-09 a GitHub runner got an empty copy while a local fetch had two rows), and a
stale fetch must never delete reports. Run daily by .github/workflows/collect-gauges.yml.

Checks (a report failing any is left out, and counted in the printout):
  - JSON version 1, every field of the expected kind and range
  - the reported time no later than 10 min after it was submitted, and no more than
    2 days (plus 10 min) before
  - the place: km 0 to Kholo Creek, a bank, and within 350 m of the centreline
  - no exact repeat of an accepted report (double taps)
Aliases are trimmed to 30 characters; one containing a web address is blanked.

Usage:
  python collect_reports.py --out DIR         # DIR: a checkout of the reports branch
  python collect_reports.py --out DIR --csv FILE   # test with a saved copy of the CSV

Uses only the standard library, like collect_gauges.py.
"""
import argparse
import csv
import io
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from collect_gauges import USER_AGENT

HERE = Path(__file__).parent
PUBLIC_CSV = ("https://docs.google.com/spreadsheets/d/e/2PACX-1vRREHLIOYMjz8rcYs-_mt-aLazFHzp3lFRzzXA9"
              "XrAIan_E_RbwgQsUmtzP5DU9097hakfMS1twYsh2/pub?gid=1809157979&single=true&output=csv")
HIDDEN_CSV = HERE / "data" / "reports_hidden.csv"

FIELDS = ["submitted_aest", "time_aest", "km", "bank", "alias", "dir_kind", "dir", "strength",
          "speed_kmh", "clarity", "problems", "verdict"]
DIRS = {"up", "down", "slack", "swirl"}
BANKS = {"mid", "left", "right"}
PROBLEMS = {"debris", "rubbish", "foam", "oil", "algae", "smell", "dead_fish"}
VERDICTS = {"match", "turn", "mismatch", "none"}
MAX_OFF_M = 350                  # as build_report.MAX_OFF_M
KM_MAX = 75.8 + 0.2              # Kholo Creek, as the page allows
SLACK_TIME = timedelta(minutes=10)
MAX_AGE = timedelta(days=2)


class _KeepRedirect(urllib.request.HTTPRedirectHandler):
    """Don't follow redirects; fetch_csv follows them itself."""
    def redirect_request(self, *args, **kwargs):
        return None


def fetch_csv(url, hops=3):
    """GET url, following redirects with the Location exactly as given.

    Google answers a published-sheet URL with a redirect to googleusercontent.com whose
    path contains "*" and "@". urllib's own redirect handling percent-encodes those and
    the new URL then fails with 401, so redirects are followed by hand here.
    """
    opener = urllib.request.build_opener(_KeepRedirect)
    for _ in range(hops + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with opener.open(req, timeout=120) as resp:
                return resp.read().decode("utf-8-sig")
        except urllib.error.HTTPError as e:
            if e.code not in (301, 302, 303, 307, 308) or not e.headers.get("Location"):
                raise
            url = e.headers["Location"]
    raise SystemExit(f"Too many redirects from {url}")


def hidden_times():
    """Submission times (as in the CSV) of reports hidden by hand."""
    if not HIDDEN_CSV.exists():
        return set()
    with HIDDEN_CSV.open(newline="") as f:
        return {r["submitted_aest"].strip() for r in csv.DictReader(f)}


def is_num(x, lo, hi):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and lo <= x <= hi


def check(submitted, raw):
    """The report as a CSV row (dict), or a reason string if it's rejected."""
    try:
        sub = datetime.strptime(submitted, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return "bad submission time"
    try:
        r = json.loads(raw)
    except ValueError:
        return "not JSON"
    if not isinstance(r, dict) or r.get("v") != 1:
        return "not version 1"
    try:
        t = datetime.strptime(str(r.get("time")), "%Y-%m-%dT%H:%M")
    except ValueError:
        return "bad time"
    if t > sub + SLACK_TIME:
        return "time after submission"
    if t < sub - MAX_AGE - SLACK_TIME:
        return "time too long before submission"
    if not is_num(r.get("km"), 0, KM_MAX):
        return "km out of range"
    if r.get("bank") not in BANKS:
        return "bad bank"
    if r.get("off_m") is not None and not is_num(r.get("off_m"), 0, MAX_OFF_M):
        return "too far from the river"
    if r.get("dir_kind") != "river" or r.get("dir") not in DIRS:
        return "bad direction"
    s = r.get("strength")
    if not (s is None and r["dir"] == "swirl") and not (isinstance(s, int) and 0 <= s <= 4):
        return "bad strength"
    if r.get("speed_kmh") is not None and not is_num(r.get("speed_kmh"), 0, 20):
        return "bad speed"
    c = r.get("clarity")
    if c is not None and not (isinstance(c, int) and 1 <= c <= 5):
        return "bad clarity"
    p = r.get("problems")
    if not isinstance(p, list) or not set(p) <= PROBLEMS:
        return "bad problems list"
    if r.get("verdict") not in VERDICTS:
        return "bad verdict"
    alias = re.sub(r"[\x00-\x1f\x7f]", "", str(r.get("alias") or "")).strip()[:30]
    if re.search(r"https?:|www\.|\.(com|net|org|au)\b", alias, re.I):
        alias = ""
    return {"submitted_aest": submitted, "time_aest": t.strftime("%Y-%m-%d %H:%M"),
            "km": f"{r['km']:.1f}", "bank": r["bank"], "alias": alias,
            "dir_kind": "river", "dir": r["dir"], "strength": "" if s is None else str(s),
            "speed_kmh": "" if r.get("speed_kmh") is None else f"{r['speed_kmh']:.1f}",
            "clarity": "" if c is None else str(c), "problems": ";".join(sorted(p)),
            "verdict": r["verdict"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="folder to write into (reports branch checkout)")
    ap.add_argument("--csv", help="read this saved CSV instead of fetching the published one")
    args = ap.parse_args()

    text = Path(args.csv).read_text() if args.csv else fetch_csv(PUBLIC_CSV)
    rows = list(csv.DictReader(io.StringIO(text)))
    hidden = hidden_times()
    accepted, rejected, seen = [], {}, set()
    for row in rows:
        sub, raw = row.get("submitted_aest", "").strip(), row.get("report", "")
        if not sub:
            continue
        if sub in hidden:
            rejected["hidden by hand"] = rejected.get("hidden by hand", 0) + 1
            continue
        res = check(sub, raw)
        if isinstance(res, str):
            rejected[res] = rejected.get(res, 0) + 1
            continue
        key = tuple(v for k, v in res.items() if k != "submitted_aest")
        if key in seen:
            rejected["repeat"] = rejected.get("repeat", 0) + 1
            continue
        seen.add(key)
        accepted.append(res)

    folder = Path(args.out) / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    # Keep what's saved; a report fetched again replaces its saved copy. Hidden ones
    # go, whether saved or new.
    ident = lambda r: (r["submitted_aest"], r["time_aest"], r["km"], r["bank"], r["dir"])
    saved = {}
    for old in sorted(folder.glob("*.csv")):
        with old.open(newline="") as f:
            for r in csv.DictReader(f):
                saved[ident(r)] = r
        old.unlink()                     # rewritten in full below
    n_saved = len(saved)
    saved.update({ident(r): r for r in accepted})
    keep = [r for r in saved.values() if r["submitted_aest"] not in hidden]
    print(f"{n_saved} reports already saved, {len(keep)} after this run")
    by_month = {}
    for r in sorted(keep, key=lambda r: (r["time_aest"], r["submitted_aest"])):
        by_month.setdefault(r["time_aest"][:7], []).append(r)
    for month, rs in by_month.items():
        with (folder / f"{month}.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
            w.writeheader()
            w.writerows(rs)
    print(f"{len(rows)} rows: {len(accepted)} accepted"
          + "".join(f", {n} {why}" for why, n in sorted(rejected.items())))


if __name__ == "__main__":
    main()
