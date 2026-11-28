"""Which river a place is on (roadmap item 6).

A place in this project is (river, km): km is chainage along that river's own
centreline. The Brisbane River runs from the Bar (km 0); a branch (a tributary of the
Brisbane, such as the Bremer, item 19) has km 0 at its confluence and is listed in
data/rivers.csv with its parent and the parent's km at the confluence.

Every data file with a km has a river column (stations, features, observations, ramps,
gauges, and the reports CSV). A blank river means brisbane, so files and reports made
before the column existed keep their meaning.

Standard library only (collect_reports.py runs with no extra packages).
"""
import csv
from pathlib import Path

DATA = Path(__file__).parent / "data"
DEFAULT = "brisbane"


def load(path=DATA / "rivers.csv"):
    """{river id: row dict} from data/rivers.csv, in file order."""
    with open(path, newline="") as f:
        return {r["river"]: r for r in csv.DictReader(f)}


def ids(path=DATA / "rivers.csv"):
    """The river ids, e.g. {"brisbane"}."""
    return set(load(path))


def norm(value):
    """A river value as stored: stripped and lower case, blank or missing = brisbane."""
    # value != value: pandas reads a blank cell as NaN, which is not equal to itself.
    v = "" if value is None or value != value else str(value).strip().lower()
    return v or DEFAULT


def only(df, river=DEFAULT):
    """Rows of a pandas DataFrame on one river (a blank or missing river column counts
    as brisbane). The index is kept, so callers that reset it still do."""
    if "river" not in df.columns:
        return df if river == DEFAULT else df.iloc[0:0]
    return df[df["river"].map(norm) == river]
