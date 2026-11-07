#!/usr/bin/env python3
"""Build a Brisbane River centreline (Bar -> upstream) from QLD watercourse lines.

Steps:
  1. Download the "Brisbane River" segments of the QLD "Watercourse lines - Queensland"
     layer and save the response unchanged (data/qld_watercourse_brisbane_river.geojson).
     Skip this with --no-fetch to reuse the saved file.
  2. Join the segments into a network and take the shortest path from the river mouth
     to the most upstream point reached in the download box (this drops the duplicate
     channels around islands).
  3. Add a straight segment from the mouth end of the line to the Brisbane Bar gauge.
  4. Write data/centreline.csv: ordered lon, lat and chainage_km (0 = gauge).
  5. Snap each station in stations.csv onto the line and print a check report.
     stations.csv is only changed with --write-stations; review the report first.

Usage:
  python build_centreline.py              # download, build, report
  python build_centreline.py --no-fetch   # rebuild from the saved download
  python build_centreline.py --no-fetch --write-stations   # also update chainage_km

Sources:
  - Watercourse lines - Queensland (Department of Resources), CC BY 4.0:
    https://www.data.qld.gov.au/dataset/hydrographic-features-queensland-series
    ArcGIS service: InlandWaters/WaterCoursesAndBodies/MapServer, layer 33
  - Brisbane Bar (Whyte Island) gauge position, 27 deg 24.096' S, 153 deg 9.444' E:
    https://www.qld.gov.au/environment/coasts-waterways/beach/tide-sites/brisbane-bar
"""
import argparse
import csv
import hashlib
import heapq
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
DATA = HERE / "data"
RAW = DATA / "qld_watercourse_brisbane_river.geojson"
OUT = DATA / "centreline.csv"

SERVICE = ("https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
           "InlandWaters/WaterCoursesAndBodies/MapServer/33/query")
# Download box (lon_min, lat_min, lon_max, lat_max): mouth to just past Mt Crosby.
BBOX = (152.70, -27.65, 153.25, -27.30)

# Brisbane Bar (Whyte Island) gauge, from the qld.gov.au tide-site page (see Sources).
GAUGE_LON = 153 + 9.444 / 60
GAUGE_LAT = -(27 + 24.096 / 60)

R_EARTH = 6371.0088  # km, mean Earth radius
LAT0 = -27.5         # reference latitude for the local flat projection


def to_xy(lon, lat):
    """Lon/lat (degrees) -> local flat x/y in km. An equirectangular projection centred
    on LAT0. Over this area (about 0.3 deg of latitude) the east-west scale error is
    under 0.2 %, which is well inside the uncertainty of the station positions."""
    lon = np.asarray(lon, float)
    lat = np.asarray(lat, float)
    x = np.radians(lon) * R_EARTH * math.cos(math.radians(LAT0))
    y = np.radians(lat) * R_EARTH
    return x, y


def fetch(path):
    """Download the Brisbane River segments as GeoJSON and save the bytes unchanged."""
    q = {
        "where": "name='Brisbane River'",
        "geometry": ",".join(str(v) for v in BBOX),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "objectid,name,feature_type,function,feature_source,feature_date",
        "outSR": "4326",
        "f": "geojson",
    }
    url = SERVICE + "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"User-Agent": "Brisbane-river-tides/0.2"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
    j = json.loads(body)
    if "error" in j:
        raise SystemExit(f"Service error: {j['error']}")
    if j.get("exceededTransferLimit") or j.get("properties", {}).get("exceededTransferLimit"):
        raise SystemExit("Service returned a partial result (transfer limit). Narrow BBOX.")
    path.write_bytes(body)
    print(f"Downloaded {len(j['features'])} segments -> {path}")


def load_lines(path):
    """Return a list of polylines, each a list of (lon, lat)."""
    j = json.loads(path.read_text(encoding="utf-8"))
    lines = []
    for f in j["features"]:
        g = f["geometry"]
        parts = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        lines += [[tuple(c[:2]) for c in p] for p in parts if len(p) > 1]
    return lines


def line_length(coords):
    x, y = to_xy([c[0] for c in coords], [c[1] for c in coords])
    return float(np.hypot(np.diff(x), np.diff(y)).sum())


def build_network(lines):
    """Graph whose nodes are segment end points (rounded so touching ends match)
    and whose edges are the segments, weighted by length in km."""
    key = lambda c: (round(c[0], 7), round(c[1], 7))
    adj = {}
    for i, ln in enumerate(lines):
        a, b, w = key(ln[0]), key(ln[-1]), line_length(ln)
        adj.setdefault(a, []).append((b, w, i, False))
        adj.setdefault(b, []).append((a, w, i, True))   # True = walk segment backwards
    return adj


def dijkstra(adj, src):
    dist, prev = {src: 0.0}, {}
    pq = [(0.0, src)]
    while pq:
        d, n = heapq.heappop(pq)
        if d > dist[n]:
            continue
        for m, w, i, rev in adj[n]:
            nd = d + w
            if nd < dist.get(m, math.inf):
                dist[m], prev[m] = nd, (n, i, rev)
                heapq.heappush(pq, (nd, m))
    return dist, prev


def main_stem(lines):
    """Shortest path from the mouth end (node nearest the gauge) to the node farthest
    from it along the network (the upstream limit of the download)."""
    adj = build_network(lines)
    nodes = list(adj)
    nx, ny = to_xy([n[0] for n in nodes], [n[1] for n in nodes])
    gx, gy = to_xy(GAUGE_LON, GAUGE_LAT)
    mouth = nodes[int(np.argmin(np.hypot(nx - gx, ny - gy)))]
    dist, prev = dijkstra(adj, mouth)
    top = max(dist, key=dist.get)

    used, coords, n = [], [], top
    while n != mouth:
        p, i, rev = prev[n]
        # rev=True means the walk p -> n runs against the stored direction of segment i.
        seg = lines[i][::-1] if rev else lines[i]   # orient each segment mouth -> upstream
        used.append(i)
        coords = seg[:-1] + coords if coords else seg
        n = p
    unreached = len(nodes) - len(dist)
    return coords, mouth, top, used, unreached, adj


def report_branches(lines, used, adj):
    """List segments not on the main stem that are connected to it (side channels)."""
    on = set(used)
    side = [i for i in range(len(lines)) if i not in on]
    total = sum(line_length(lines[i]) for i in side)
    print(f"Segments: {len(lines)} total, {len(used)} on main stem, {len(side)} left out "
          f"({total:.2f} km of side channels or disconnected pieces)")


def chainage(coords):
    x, y = to_xy([c[0] for c in coords], [c[1] for c in coords])
    return np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])


def snap(px, py, x, y, ch):
    """Nearest point on the polyline (x, y, chainage ch) to (px, py).
    Returns distance to every vertex segment so ambiguity can be checked."""
    ax, ay, bx, by = x[:-1], y[:-1], x[1:], y[1:]
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / np.where(L2 == 0, 1, L2), 0, 1)
    qx, qy = ax + t * dx, ay + t * dy
    d = np.hypot(px - qx, py - qy)              # distance to each segment
    seg_ch = ch[:-1] + t * np.diff(ch)          # chainage of the closest point on each
    return d, seg_ch


def station_report(coords, ch, stations_path, sep_km=2.0):
    """Snap stations and flag any whose position is nearly as close to a different
    reach of river (>= sep_km of chainage away). Those are likely on the wrong bend."""
    x, y = to_xy([c[0] for c in coords], [c[1] for c in coords])
    rows = list(csv.DictReader(open(stations_path, encoding="utf-8")))
    print(f"\nStation check (stations.csv positions are rounded to ~1 arc-minute, "
          f"so snap distances up to ~1.5 km are expected)")
    print(f"{'station':32s} {'old km':>7s} {'new km':>7s} {'snap m':>7s}  "
          f"{'2nd reach':>16s}  flag")
    out = []
    for r in rows:
        if not r["lat"]:
            continue
        px, py = to_xy(float(r["lon"]), float(r["lat"]))
        d, sch = snap(px, py, x, y, ch)
        i = int(np.argmin(d))
        best_d, best_ch = d[i], sch[i]
        far = np.abs(sch - best_ch) >= sep_km
        alt = f"{sch[far][np.argmin(d[far])]:5.1f} km @{d[far].min()*1000:5.0f} m" if far.any() else "-"
        ambiguous = far.any() and d[far].min() < best_d + 0.5   # within 500 m of the best
        flag = "AMBIGUOUS" if ambiguous else ""
        old = float(r["chainage_km"]) if r["chainage_km"] else math.nan
        print(f"{r['name']:32s} {old:7.1f} {best_ch:7.2f} {best_d*1000:7.0f}  {alt:>16s}  {flag}")
        out.append((r["name"], best_ch))
    order_ok = all(a[1] <= b[1] for a, b in zip(out, out[1:]))
    print(f"\nNew chainage increases in stations.csv order: {'yes' if order_ok else 'NO - check flagged stations'}")
    return dict(out), order_ok


def write_stations(stations_path, new_ch):
    """Replace chainage_km in stations.csv with the snapped values (1 decimal, which
    matches their ~1 km uncertainty). Every other column, and the file's line
    endings, are kept as they were."""
    eol = "\r\n" if b"\r\n" in Path(stations_path).read_bytes() else "\n"
    with open(stations_path, encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f)
        fields, rows = rd.fieldnames, list(rd)
    for r in rows:
        if r["name"] in new_ch:
            r["chainage_km"] = f"{new_ch[r['name']]:.1f}"
    with open(stations_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator=eol)
        w.writeheader()
        w.writerows(rows)
    print(f"Updated chainage_km in {stations_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true", help="reuse the saved download")
    ap.add_argument("--stations", default=str(DATA / "stations.csv"))
    ap.add_argument("--write-stations", action="store_true",
                    help="write the snapped chainage into stations.csv (review the report first)")
    a = ap.parse_args()

    if not a.no_fetch:
        fetch(RAW)
    print(f"Raw file SHA-256: {hashlib.sha256(RAW.read_bytes()).hexdigest()}")

    lines = load_lines(RAW)
    coords, mouth, top, used, unreached, adj = main_stem(lines)
    report_branches(lines, used, adj)
    if unreached:
        print(f"Segment end points not connected to the main stem: {unreached}")

    # Join the gauge to the mouth end of the line.
    gap = chainage([(GAUGE_LON, GAUGE_LAT), coords[0]])[-1]
    coords = [(GAUGE_LON, GAUGE_LAT)] + coords
    print(f"Gauge -> line mouth end: {gap*1000:.0f} m straight segment added")
    print(f"Upstream end: {top[0]:.5f}, {top[1]:.5f}")

    ch = chainage(coords)
    print(f"Centreline: {len(coords)} vertices, {ch[-1]:.2f} km gauge -> upstream end")

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["lon", "lat", "chainage_km"])
        for (lon, lat), c in zip(coords, ch):
            w.writerow([f"{lon:.6f}", f"{lat:.6f}", f"{c:.4f}"])
    print(f"Wrote {OUT}")

    new_ch, order_ok = station_report(coords, ch, a.stations)
    if a.write_stations:
        if not order_ok:
            raise SystemExit("Not writing stations.csv: chainage order does not match the file.")
        write_stations(a.stations, new_ch)


if __name__ == "__main__":
    main()
