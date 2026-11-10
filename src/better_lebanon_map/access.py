"""Access paths: the driveway, track or footpath a building is reached by, when it does not front a street.

A building takes the nearest street (addressing.assign_streets). That is wrong for a house at the
end of a driveway OSM does not have: the house at the end of a 75 m drive off Rue Broumana in
Jouret Ballout is nearer to Rue des Chênes, which it cannot reach. Four sources give the driveway:

- streets chosen in the viewer by people who know the house ("this is the right street" on its
  address card, saved by `serve` in data/corrections/streets.jsonl): one line per house with its
  building and the point of the street it is reached from. They always apply.

- paths drawn by people who know the place, in data/corrections/access.geojson: LineStrings in
  WGS84 from the street to the house (either way round). They always apply.
- the driveways, tracks, footways and steps OSM maps, which are not streets (network.py leaves
  them out): a group of them that meets exactly one street leads from it to the buildings beside
  them that do not front a street (FRONTAGE_M), up to MAX_TRACK_M along the way and MAX_SERVED
  buildings from one junction (Mapped).
- roads Microsoft detected in satellite imagery (github.com/microsoft/RoadDetections, ODbL), kept
  for Lebanon in data/raw/ms_roads/lebanon.tsv, where no OSM way runs: a detected track that
  leaves one OSM street and ends without reaching another, passing within HOUSE_M of a building
  that does not front a street itself (FRONTAGE_M).

The building then belongs to the street the path leaves and is numbered where it leaves it, on
that side: addressing.metric_numbers numbers it by its `anchor`, a point beside the street there.
"""

import json
import sqlite3
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from shapely.ops import nearest_points, substring

from .localities import METRIC_CRS

JUNCTION_M = 15.0     # a path's end this close to a street leaves that street
HOUSE_M = 12.0        # a building this close to a path is reached by it...
CENTER_M = 30.0       # ... when its center is this close too (not a large building's far corner)
FRONTAGE_M = 25.0     # a building this close to its nearest street fronts it: imagery does not move it
COVERED_M = 8.0       # a detected road this close to an OSM way is that way
SAMPLE_M = 4.0
MIN_TRACK_M = 15.0
MAX_TRACK_M = 150.0   # longer tracks are roads of their own, not driveways (OSM's: from the street on)
HEADING_M = 15.0      # the side a path leaves on is where it is this far from the street
MAX_SERVED = 10       # an OSM way reaching more buildings from one junction is a lane (alleys, greenhouse rows)
PATHS = {"track", "footway", "steps"}   # OSM highways reaching buildings without being streets (+ service=driveway)
# judged: by the model (judge.py); approved: by a person; mapped: an OSM driveway, track, footway or steps;
# chosen: by a person who knows the house, in the viewer
KINDS = ("nearest", "drawn", "imagery", "judged", "approved", "mapped", "chosen")


def load_drawn(path):
    """The drawn paths, in metres."""
    if not Path(path).exists():
        return []
    g = gpd.read_file(path).to_crs(METRIC_CRS)
    return [x for x in g.geometry if x is not None and x.geom_type == "LineString"]


def load_chosen(path):
    """The streets chosen in the viewer: [(building key, junction on the street in metres, "chosen")],
    from lines {"key": "w123", "junction": [lon, lat]}; the last line for a house wins."""
    if not Path(path).exists():
        return []
    to_metric = Transformer.from_crs(4326, METRIC_CRS, always_xy=True)
    last = {}
    for line in Path(path).read_text().splitlines():
        if line.strip():
            doc = json.loads(line)
            last[doc["key"]] = shapely.Point(to_metric.transform(*doc["junction"]))
    return [(key, junction, "chosen") for key, junction in last.items()]


def load_judged(path):
    """The access judge's decisions (judge.py): [(building key, junction on the street in metres,
    "approved" when a person approved or corrected it, else "judged")], approved ones first. A
    junction, not a street id: ids change from one build to the next."""
    if not Path(path).exists():
        return []
    con = sqlite3.connect(path)
    rows = con.execute("SELECT key, status, choice, context FROM judgments "
                       "WHERE status IN ('auto', 'approved', 'corrected') AND choice IN ('A', 'B', 'C', 'D')").fetchall()
    con.close()
    to_metric = Transformer.from_crs(4326, METRIC_CRS, always_xy=True)
    out = []
    for key, status, choice, context in rows:
        lon, lat = json.loads(context)["candidates"]["ABCD".index(choice)]["junction"]
        out.append((key, shapely.Point(to_metric.transform(lon, lat)), "judged" if status == "auto" else "approved"))
    return sorted(out, key=lambda r: r[2] != "approved")


def load_detected(path):
    """Microsoft's detected roads in Lebanon, in metres: one "LBN<TAB>GeoJSON" row per road."""
    if not Path(path).exists():
        return np.array([], dtype=object)
    with open(path) as f:
        rows = [line.split("\t", 1)[1] for line in f if line.startswith("LBN\t")]
    g = gpd.GeoSeries(shapely.from_geojson(rows), crs=4326).to_crs(METRIC_CRS)
    return g.explode(index_parts=False).values


def unmapped_stretches(lines, osm_ways):
    """The stretches of detected roads that no OSM way runs along: runs of points farther than
    COVERED_M from every OSM way, at least MIN_TRACK_M long."""
    if not len(lines):
        return []
    xy, line_of = shapely.get_coordinates(shapely.segmentize(lines, SAMPLE_M), return_index=True)
    near = shapely.STRtree(osm_ways).query_nearest(shapely.points(xy), max_distance=COVERED_M, all_matches=False)
    covered = np.zeros(len(xy), np.int8)
    covered[near[0]] = 1
    cut = np.flatnonzero((np.diff(line_of) != 0) | (np.diff(covered) != 0)) + 1
    out = []
    for run in np.split(np.arange(len(xy)), cut):
        if len(run) >= 2 and not covered[run[0]]:
            line = shapely.LineString(xy[run])
            if line.length >= MIN_TRACK_M:
                out.append(line)
    return out


class Mapped:
    """The driveways, tracks, footways and steps OSM maps, as one graph of their OSM nodes. A group
    of connected ways that meets exactly one street (shares a node with it) leads from that street
    to the buildings beside it; a group that meets two streets or more does not say which one a
    building is reached from, and is not used."""

    def __init__(self, ways, edges):
        w = ways[ways.highway.isin(PATHS) | ((ways.highway == "service") & (ways.service == "driveway"))]
        xy, way = shapely.get_coordinates(w.geometry.values, return_index=True)
        node, at = np.unique(np.concatenate(w.nodes.values), return_inverse=True)
        self.xy = np.empty((len(node), 2))
        self.xy[at] = xy
        step = np.flatnonzero((way[:-1] == way[1:]) & (at[:-1] != at[1:]))
        self.ends, first = np.unique(np.sort(np.stack([at[step], at[step + 1]], 1), 1), axis=0, return_index=True)
        length = np.hypot(*(xy[step + 1] - xy[step]).T)[first]
        graph = csr_matrix((np.maximum(length, 1e-6), (self.ends[:, 0], self.ends[:, 1])), shape=(len(node), len(node)))
        _, group = connected_components(graph, directed=False)
        e = edges[edges.street_id >= 0]
        shared = np.flatnonzero(np.isin(node, np.concatenate(ways.nodes[ways.osm_id.isin(e.way_id)].values)))
        i, j = shapely.STRtree(e.geometry.values).query_nearest(shapely.points(self.xy[shared]), max_distance=1.0,
                                                                  all_matches=False)
        junction, street = shared[i], e.street_id.values[j]
        one = pd.Series(street).groupby(group[junction]).transform("nunique").values == 1
        self.street = np.full(len(node), -1)
        self.street[junction[one]] = street[one]
        self.dist, self.prev, _ = dijkstra(graph, directed=False, indices=junction[one], min_only=True,
                                           return_predecessors=True)
        self.segments = shapely.linestrings(self.xy[self.ends])

    def reach(self, k, footprint, point):
        """(street id, way from the street to the building) for a building beside segment k: along
        the ways from the junction to the point of k nearest the building's center, then to its
        wall; None when k's group meets no street or several."""
        seg, (a, b) = self.segments[k], self.ends[k]
        t = seg.project(point)
        via_a, via_b = self.dist[a] + t, self.dist[b] + seg.length - t
        if not np.isfinite(min(via_a, via_b)):
            return None
        route = [a if via_a <= via_b else b]
        while self.prev[route[-1]] >= 0:
            route.append(self.prev[route[-1]])
        q = seg.interpolate(t)
        wall = nearest_points(footprint, q)[0]
        coords = [*self.xy[route[::-1]], q.coords[0], *([wall.coords[0]] if wall.distance(q) > 0.5 else [])]
        return self.street[route[-1]], shapely.LineString(coords)


def beside(spine, start, path):
    """The point to number a building by: 3 m off the street where its path leaves it, on the side
    the path heads to (judged HEADING_M out, not at the junction, where the street line drawn in
    OSM and the path's first metres may cross)."""
    j = spine.project(start)
    p, a, b = (spine.interpolate(x) for x in (j, max(j - 1, 0), min(j + 1, spine.length)))
    q = path.interpolate(min(HEADING_M, path.length / 2))
    tx, ty = b.x - a.x, b.y - a.y
    norm = np.hypot(tx, ty) or 1.0
    sign = 1 if tx * (q.y - p.y) - ty * (q.x - p.x) > 0 else -1   # left of the street's direction
    return shapely.Point(p.x - ty / norm * 3 * sign, p.y + tx / norm * 3 * sign)


def attach(bld, edges, streets, drawn, detected, ways, judged=()):
    """bld as addressing.assign_streets leaves it (street_id -1 when no street is near); ways: the
    raw OSM highways in metres, with their nodes; judged: the streets chosen in the viewer
    (load_chosen) and the access judge's (load_judged). Buildings reached by a drawn path, a street
    a person chose in the viewer or approved with the access judge, a way OSM maps (Mapped), the
    model's own judged street or a detected track, in that order, get its street, an `anchor` to
    number them by, the path from the street to the building (`access_path`) and `access` "drawn",
    "chosen", "approved", "mapped", "judged" or "imagery"; the others "nearest"."""
    bld = bld.copy()
    access, anchor, paths = np.full(len(bld), "nearest", dtype=object), [None] * len(bld), [None] * len(bld)
    street, dist = bld.street_id.values.copy(), bld.dist_to_street.values.copy()
    e = edges[edges.street_id >= 0]
    spines = streets.set_index("street_id").spine
    etree, btree = shapely.STRtree(e.geometry.values), shapely.STRtree(bld.geometry.values)
    points, footprints = bld["point"].values, bld.geometry.values

    def street_at(pt):
        i, d = etree.query_nearest(pt, max_distance=JUNCTION_M, return_distance=True, all_matches=False)
        return (i[0], d[0]) if len(i) else (None, np.inf)

    def use(path, kind):
        a, b = shapely.Point(path.coords[0]), shapely.Point(path.coords[-1])
        (ia, da), (ib, db) = street_at(a), street_at(b)
        if kind == "imagery" and ((ia is None) == (ib is None) or path.length > MAX_TRACK_M):
            return 0   # not a dead end off one street
        if ia is None or (ib is not None and db < da):
            path, a, ia = path.reverse(), b, ib
        if ia is None:
            return 0
        edge = e.geometry.values[ia]
        start = shapely.line_interpolate_point(edge, shapely.line_locate_point(edge, a))
        full = shapely.LineString([start.coords[0], *path.coords])
        if kind == "drawn":   # the house the path was drawn to
            near = btree.query(shapely.Point(full.coords[-1]), predicate="dwithin", distance=HOUSE_M)
            hits = near[np.argsort(shapely.distance(footprints[near], shapely.Point(full.coords[-1])))][:1]
        else:                 # houses along the track that do not front a street
            near = btree.query(full, predicate="dwithin", distance=HOUSE_M)
            hits = [h for h in near if access[h] == "nearest" and dist[h] > FRONTAGE_M
                    and points[h].distance(full) <= CENTER_M]
        sid = e.street_id.values[ia]
        spot, n = beside(spines[sid], start, full), 0
        for h in hits:
            upto = full.project(points[h])
            reach = substring(full, 0, upto) if upto > 1 else shapely.LineString([full.coords[0], full.coords[0]])
            if reach.geom_type != "LineString":
                continue
            wall = nearest_points(footprints[h], shapely.Point(reach.coords[-1]))[0]   # the path ends at the building
            line = shapely.LineString([*reach.coords, wall.coords[0]]) if wall.distance(shapely.Point(reach.coords[-1])) > 0.5 \
                else reach
            if line.length < 1:
                continue
            access[h], street[h], dist[h], anchor[h], paths[h] = kind, sid, line.length, spot, line
            n += 1
        return n

    n_drawn = sum(use(p, "drawn") for p in drawn)
    index = {k: n for n, k in enumerate(bld.osm_type.str[0] + bld.osm_id.astype(str))}

    def judge(kind):
        """The judge's streets, met where they come nearest the building; the model's own (not a
        person's) only when it names another street than the house has."""
        n = 0
        for key, junction, k in judged:
            h = index.get(key)
            ia = street_at(junction)[0] if k == kind and h is not None and access[h] == "nearest" else None
            if ia is None or (kind == "judged" and e.street_id.values[ia] == street[h]):
                continue
            sid, edge = e.street_id.values[ia], e.geometry.values[ia]
            start = shapely.line_interpolate_point(edge, shapely.line_locate_point(edge, junction))
            wall = nearest_points(footprints[h], start)[0]
            line = shapely.LineString([start.coords[0], (wall if wall.distance(start) > 0.5 else points[h]).coords[0]])
            access[h], street[h], dist[h], anchor[h], paths[h] = kind, sid, line.length, \
                beside(spines[sid], start, line), line
            n += 1
        return n

    n_chosen, n_approved = judge("chosen"), judge("approved")
    # OSM's own driveways, tracks, footways and steps, for the buildings beside them that do not front a street.
    mapped, before_mapped = Mapped(ways, edges), street.copy()
    far = np.flatnonzero((access == "nearest") & (dist > FRONTAGE_M))
    ih, ik = shapely.STRtree(mapped.segments).query_nearest(footprints[far], max_distance=HOUSE_M, all_matches=False)
    found = []
    for h, k in zip(far[ih], ik):
        way = mapped.reach(k, footprints[h], points[h])
        if way is not None and way[1].length <= MAX_TRACK_M and points[h].distance(mapped.segments[k]) <= CENTER_M:
            found.append((h, *way))
    # Numbered one after the other where they leave the street, the buildings of a lane would push the
    # street's numbers far past its metres.
    served = Counter(line.coords[0] for _, _, line in found)
    for h, sid, line in found:
        if served[line.coords[0]] <= MAX_SERVED:
            start = shapely.Point(line.coords[0])
            access[h], street[h], dist[h], anchor[h], paths[h] = "mapped", sid, line.length, \
                beside(spines[sid], start, line), line
    n_judged = judge("judged")
    # Only the detected roads that pass near a building not fronting a street can be its driveway.
    close = shapely.STRtree(detected).query(bld.geometry.values[dist > FRONTAGE_M], predicate="dwithin",
                                            distance=HOUSE_M)[1] if len(detected) else []
    tracks = unmapped_stretches(detected[np.unique(close)], ways.geometry.values) if len(close) else []
    before_imagery = street.copy()
    n_imagery = sum(use(t, "imagery") for t in tracks)
    bld["street_id"], bld["dist_to_street"], bld["access"] = street, dist, access
    bld["anchor"] = gpd.GeoSeries(anchor, index=bld.index, crs=METRIC_CRS)
    bld["access_path"] = gpd.GeoSeries(paths, index=bld.index, crs=METRIC_CRS)
    is_mapped = access == "mapped"
    stats = {"drawn": n_drawn, "chosen": n_chosen, "approved": n_approved, "judged": n_judged, "mapped": int(is_mapped.sum()),
             "mapped_changed_street": int((is_mapped & (street != before_mapped)).sum()),
             "mapped_had_no_street": int((is_mapped & (before_mapped < 0)).sum()),
             "mapped_lanes": len(found) - int(is_mapped.sum()),
             "imagery": n_imagery, "detected_roads": len(detected), "unmapped_tracks": len(tracks),
             "imagery_changed_street": int(((access == "imagery") & (street != before_imagery)).sum())}
    return bld, stats
