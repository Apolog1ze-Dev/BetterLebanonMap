"""Routing graph for turn-by-turn directions in the viewer.

All highways (motorways, ramps, roundabouts and footpaths included, unlike the addressing
network) are cut at junctions. Each edge carries the street id of the logical street it belongs
to, so directions read "Turn left onto Rue des Cèdres". The browser loads it as one binary file:

  Float32 nodes[n_nodes*2] (lon, lat) | Int32 u[n_edges] | Int32 v[n_edges] | Float32 length_m[n_edges]
  | Int32 label[n_edges] | Int32 geom_offset[n_edges+1] | Float32 coords[n_coords*2]
  | Uint8 flags[n_edges] | Uint8 class[n_edges]

label >= 0: street id; label <= -2: route-only name -(label+2) in route.json; -1: unnamed.
flags: bit0 forward-only, bit1 backward-only, bit2 cars allowed, bit3 pedestrians allowed, bit4 roundabout.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer

from .localities import METRIC_CRS
from .naming import osm_trilingual
from .network import classify_name, name_key, specific_fr_key, way_names

CLASSES = ["motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
           "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential", "living_street",
           "service", "road", "track", "pedestrian", "footway", "steps"]
SPEED_KMH = {"motorway": 90, "motorway_link": 45, "trunk": 70, "trunk_link": 40, "primary": 60,
             "primary_link": 40, "secondary": 50, "secondary_link": 35, "tertiary": 40, "tertiary_link": 30,
             "unclassified": 30, "residential": 25, "living_street": 10, "service": 15, "road": 25, "track": 10,
             "pedestrian": 5, "footway": 5, "steps": 3}
FOOT_ONLY = {"pedestrian", "footway", "steps"}
NO_FOOT = {"motorway", "motorway_link"}
SIMPLIFY_M = 2.0


def build(raw_streets, net_edges, country, out_dir):
    s = raw_streets[raw_streets.highway.isin(CLASSES) & (raw_streets["area"] != "yes")].to_crs(METRIC_CRS)
    mids = s.geometry.interpolate(0.5, normalized=True)
    zone = country.buffer(500)
    shapely.prepare(zone)
    s = s[shapely.contains_xy(zone, mids.x, mids.y)].copy()
    shapely.prepare(country)
    mids = s.geometry.interpolate(0.5, normalized=True)
    # Ways just across the border carry the routing but not their names (no Hebrew street names).
    s["in_lebanon"] = shapely.contains_xy(country, mids.x, mids.y)

    # Which logical street each (way, node range) belongs to.
    spans = defaultdict(list)
    for w, i0, i1, sid in zip(net_edges.way_id.values, net_edges.i0.values, net_edges.i1.values,
                              net_edges.street_id.values):
        if sid >= 0:
            spans[w].append((i0, i1, int(sid)))

    # Roundabouts and ramps that carry a nearby street's name take that street's id, so directions
    # show one name in the reader's language.
    named_net = net_edges[(net_edges.street_id >= 0) & net_edges["name"].notna()]
    mids = named_net.geometry.interpolate(0.5, normalized=True)
    by_key = defaultdict(list)
    for n, fr, en, sid, pt in zip(named_net["name"], named_net.name_fr_osm, named_net.name_en_osm,
                                  named_net.street_id, mids.values):
        for k in (name_key(n, en), specific_fr_key(n, fr)):
            if k:
                by_key[k].append((pt.x, pt.y, int(sid)))

    def street_named_like(name, fr, en, xy):
        best = None
        for k in (name_key(name, en), specific_fr_key(name, fr)):
            for x, y, sid in by_key.get(k, ()):
                d = (x - xy[0]) ** 2 + (y - xy[1]) ** 2
                if d < 1500 ** 2 and (best is None or d < best[0]):
                    best = (d, sid)
        return best[1] if best else None

    counts = Counter(n for nodes in s.nodes for n in nodes)
    node_idx, node_xy = {}, []
    names, name_idx, spelled = [], {}, {}
    u_l, v_l, len_l, label_l, flag_l, cls_l, geoms = [], [], [], [], [], [], []
    for w in s.itertuples():
        nodes = list(w.nodes)
        coords = shapely.get_coordinates(w.geometry)
        cuts = [i for i, n in enumerate(nodes) if i == 0 or i == len(nodes) - 1 or counts[n] > 1]
        oneway = w.oneway in ("yes", "1", "true") or w.junction in ("roundabout", "circular") or w.highway == "motorway"
        backward = w.oneway == "-1"
        flags = (1 if oneway and not backward else 0) | (2 if backward else 0) \
            | (4 if w.highway not in FOOT_ONLY else 0) | (8 if w.highway not in NO_FOOT else 0) \
            | (16 if w.junction in ("roundabout", "circular") else 0)
        route_name = None
        name, name_fr, name_en = way_names(w) if w.in_lebanon else (None, None, None)
        named_way = bool(name) and classify_name(name)[0] == "real"
        if named_way:   # "Rue 75": a code, read as unnamed
            key = (name, name_fr, name_en)
            if key not in spelled:
                spelled[key] = osm_trilingual(*key)
            # A name some word of which would be spelled letter by letter in another script (a
            # campus path "Chemin Courts Tennis") is left out of the directions.
            if not spelled[key][3]:
                if key not in name_idx:
                    name_idx[key] = len(names)
                    names.append(key)
                route_name = name_idx[key]
        for a, b in zip(cuts[:-1], cuts[1:]):
            seg = coords[a:b + 1]
            length = float(np.sum(np.hypot(*np.diff(seg, axis=0).T)))
            if length < 0.1:
                continue
            sid = next((t for i0, i1, t in spans.get(w.osm_id, ()) if i0 <= a and b <= i1), None)
            if sid is None and named_way:
                sid = street_named_like(name, name_fr, name_en, seg[len(seg) // 2])
            label = sid if sid is not None else (-(route_name + 2) if route_name is not None else -1)
            for n, xy in ((nodes[a], seg[0]), (nodes[b], seg[-1])):
                if n not in node_idx:
                    node_idx[n] = len(node_xy)
                    node_xy.append(xy)
            u_l.append(node_idx[nodes[a]])
            v_l.append(node_idx[nodes[b]])
            len_l.append(length)
            label_l.append(label)
            flag_l.append(flags)
            cls_l.append(CLASSES.index(w.highway))
            geoms.append(shapely.LineString(seg))

    to_wgs = Transformer.from_crs(METRIC_CRS, "EPSG:4326", always_xy=True)
    simple = shapely.simplify(np.array(geoms, dtype=object), SIMPLIFY_M)
    counts_per = shapely.get_num_coordinates(simple)
    offsets = np.concatenate([[0], np.cumsum(counts_per)]).astype(np.int32)
    flat = shapely.get_coordinates(simple)
    lon, lat = to_wgs.transform(flat[:, 0], flat[:, 1])
    nxy = np.array(node_xy)
    nlon, nlat = to_wgs.transform(nxy[:, 0], nxy[:, 1])

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    parts = [
        np.column_stack([nlon, nlat]).astype(np.float32).ravel(),
        np.array(u_l, dtype=np.int32), np.array(v_l, dtype=np.int32), np.array(len_l, dtype=np.float32),
        np.array(label_l, dtype=np.int32), offsets,
        np.column_stack([lon, lat]).astype(np.float32).ravel(),
        np.array(flag_l, dtype=np.uint8), np.array(cls_l, dtype=np.uint8),
    ]
    with open(out / "route.bin", "wb") as f:
        for p in parts:
            f.write(p.astype(p.dtype.newbyteorder("<"), copy=False).tobytes())
    # Route-only names get the same Arabic / French / English treatment as streets, and the same
    # flags: "review" lists those with a word spelled letter by letter (none: they are left out
    # above), "transcribed" those whose Arabic is a transcription of a Latin-only name.
    named = [spelled[key] for key in names]
    meta = {
        "nodes": len(node_xy), "edges": len(u_l), "coords": int(offsets[-1]),
        "classes": CLASSES, "speed_kmh": SPEED_KMH,
        "names": [list(t[:3]) for t in named],
        "review": [i for i, t in enumerate(named) if t[3]],
        "transcribed": [i for i, t in enumerate(named) if t[4]],
    }
    (out / "route.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")))
    return meta
