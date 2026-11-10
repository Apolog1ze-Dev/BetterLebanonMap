"""OSM highway ways -> logical streets, each with one reference line ("spine") to number along.

OSM splits a street into many ways and leaves most of Lebanon's streets unnamed, so:
  * ways are cut into edges at junctions;
  * named edges are grouped per commune by name (small mapping gaps bridged);
  * unnamed edges are chained into "strokes": at each junction the pair of edges that
    continues straightest (deflection < MAX_DEFLECTION) is joined, the way a driver would
    say "keep going straight".
"""

import math
import re
from collections import Counter, defaultdict, deque

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from .localities import METRIC_CRS, assign
from .translit import (EN_TRAILING_TYPES, fix_ar, has_arabic, has_latin, latin_matches, latin_to_ar,
                       register_gazetteer, split_bilingual, strip_accents)

ADDRESSABLE = {"trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
               "living_street", "pedestrian", "service", "road"}
SERVICE_SKIP = {"driveway", "parking_aisle", "drive-through", "emergency_access"}
CLASS_RANK = {"trunk": 6, "primary": 5, "secondary": 4, "tertiary": 3, "unclassified": 2,
              "residential": 2, "living_street": 1, "pedestrian": 1, "road": 1, "service": 0}
MAX_DEFLECTION = 45.0      # degrees; above this a junction ends the stroke
MAIN_ROADS = {"trunk", "primary", "secondary", "tertiary"}
PROPAGATE_DEFLECTION = 30.0  # a main road's name carries on through straighter junctions than this
PROPAGATE_MAX_M = 5_000.0
SERVICE_MISMATCH = 20.0    # degrees of penalty for chaining a service road onto a street
# Same-named pieces of a commune closer than this are one street: OSM draws a street in pieces and
# drops its name for a stretch. Farther apart they are two streets, which naming.py tells apart: a
# street is one place. A code is not a name ("شارع 65" is Street 65 of each Beirut sector it
# appears in), so pieces that share only a code join across no more than a junction's width.
BRIDGE_GAP_M = 300.0       # four times this along a main road, whose name OSM drops for longer
CODE_GAP_M = 60.0
DIRECTION_SAMPLE_M = 20.0

GENERIC_NUMBERED = re.compile(
    r"^\s*(?:(?:شارع|طريق|زاروب|زقاق|ش\.?|street|st\.?|rue|road|rd\.?)\s*(?:رقم|no\.?|n°|#)?\s*)?"
    r"(?:[a-zA-Zأ-ي]\s?-?\s?)?([0-9٠-٩]+)(?:\s*[-./]\s*[0-9٠-٩]+)?\s*[a-zA-Zأ-ي]?\s*$", re.IGNORECASE)
GENERIC_LETTER = re.compile(r"^\s*(?:(?:شارع|طريق|زاروب|street|rue|road|impasse|lane|ruelle)\s+)?[A-Za-zأ-ي]\s*$",
                            re.IGNORECASE)   # "Rue A", "Impasse B", a bare "a"
GENERIC_ORDINAL = re.compile(r"^\s*([0-9]+)\s*(?:e|ème|eme|er|th|st|nd|rd)?\s*(?:rue|street|road)\s*$", re.IGNORECASE)
GENERIC_WORDS = {"شارع", "طريق", "زاروب", "الطريق العام", "طريق عام", "الطريق الرئيسي", "طريق رئيسي",
                 "الطريق الرئيسيه", "طريق رئيسيه", "الشارع العام", "شارع عام",
                 "الشارع الرئيسي", "شارع رئيسي", "طريق فرعي", "الطريق الفرعي", "main road", "main street",
                 "road", "street", "rue", "unnamed", "no name", "impasse", "ruelle", "chemin", "passage",
                 "allée", "allee", "lane", "path", "avenue", "boulevard", "route", "town", "village", "city"}
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
CODE_TYPES = {"شارع", "سارع", "طريق", "زاروب", "زقاق", "زنقة", "جادة", "فرع", "فرعي", "قرع", "street", "st",
              "rue", "road", "rd", "route", "impasse", "avenue", "lane"}
ZONE_STREET = re.compile(r"^zone \w+ - rue \d+$", re.IGNORECASE)
ROUTE_NUMBER = re.compile(r"\s*\(\s*[0-9٠-٩]+\s*\)\s*$")   # "شارع حارة حريك (96)"


def is_code(name):
    """A municipal code rather than a name: 'Street 14-G-3-A', 'Rue PV3/2', 'زنقة 22', '800 شارع',
    'شارع في 1' (street V1), 'الينار 1/17', 'Zone Verte - Rue 2'. Only street-type words, numbers and
    one- or two-letter codes, so 'Rue du 6 Mai' and 'شارع 100 متر' stay names."""
    t = name.lower().translate(ARABIC_DIGITS).strip()
    if ZONE_STREET.match(t) or re.search(r"\d\s*/\s*\d+$", t) or "_" in t:   # "Street_uni_1": an identifier
        return True
    tokens = re.findall(r"[0-9]+|[a-z]+|[ء-ي]+", t)
    return any(x.isdigit() for x in tokens) and all(
        x.isdigit() or x in CODE_TYPES or len(x) <= 2 or x == "عين" for x in tokens)   # "شارع عين 3": letter ع


def normalize(name):
    s = re.sub(r"[ً-ْـ]", "", name.strip().lower()).translate(ARABIC_DIGITS)
    s = s.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"}))
    return re.sub(r"\s+", " ", s)


# Only the Arabic street word is ignored ("شارع جورج زوين" and "جورج زوين" are one street); French
# keys keep theirs, so a "Rue X" is never merged with a different "Avenue X".
TYPE_WORD = re.compile(r"^(شارع|طريق|جاده|زاروب|(?:ال)?اوتوستراد|(?:ال)?اتستراد)\s+")


def _letters(text):
    """Letters and digits only, without a leading or trailing street-type word, route number or
    Arabic article ("شارع خوري وبارود" and "شارع الخوري و بارود" are one street)."""
    t = TYPE_WORD.sub("", normalize(strip_accents(ROUTE_NUMBER.sub("", text))))
    t = re.sub(r"(^|\s)ال(?!له)(?=\S\S)", r"\1", t)   # not "الله": "عبد الله" stays "عبدالله"
    return re.sub(r"[^\w]|_", "", t)


def name_key(name, name_en=None):
    """The Arabic name a street will be shown with, letters and digits only."""
    if not isinstance(name, str) or not name.strip():
        return None
    shown = name if has_arabic(name) else latin_to_ar(name_en if isinstance(name_en, str) else name)
    return "a:" + (_letters(shown) or normalize(name))


def specific_fr_key(name, name_fr):
    """A specific French name ("Rue Jamil Houssami"); never a generic one ("Rue 42"), since Beirut
    tags real street names with their municipal number in French."""
    fr = name_fr if isinstance(name_fr, str) else (name if isinstance(name, str) and not has_arabic(name) else None)
    if isinstance(fr, str) and classify_name(fr)[0] == "real" and _letters(fr):
        return "f:" + _letters(fr)
    return None


def way_names(w):
    """(name, name:fr, name:en) of an OSM way; the first of several values ("Rue des Jardins;Rue
    des Oliviers"). A way tagged only "name:fr" or "name:en" is still named. When `name` is not
    Arabic but name:ar is a real name ("Rue Jérusalem" / "شارع القدس"), name:ar is the name and the
    Latin one fills the French or English tag it belongs to."""
    def first(v):   # the first of several values, without a doubled type word ("شارع شارع التجارة")
        v = v.split(";")[0].strip() if isinstance(v, str) and v.strip() else None
        return fix_ar(re.sub(r"^(\S+) \1 ", r"\1 ", v)) if v else v
    fr, en, ar = first(w.name_fr), first(w.name_en), first(getattr(w, "name_ar", None))
    name = next((v for v in (first(w.name), fr, en) if v), None)
    both_ar, both_latin = split_bilingual(name)   # "Fadous-فدعوس": one name in each script
    if both_ar:
        name, fr = both_ar, fr or both_latin
    if ar and has_arabic(ar) and not has_arabic(name) and classify_name(ar)[0] == "real":
        if name and has_latin(name):
            if name.split()[-1].lower() in EN_TRAILING_TYPES:   # "El Deir Street"
                en = en or name
            else:
                fr = fr or name
        name = ar
    elif ar and has_arabic(name) and _ar_letters(ar) != _ar_letters(name):
        # name:ar left over from another name of the way ("شارع ألفريد نقاش" tagged name:ar "شارع
        # مدرسة الحكمة"): its Latin tags may translate that one; keep those that match the name.
        fr, en = (t if latin_matches(t, name) else None for t in (fr, en))
    return name, fr, en


def _ar_letters(name):
    """An Arabic name's letters alone: "شارع69" and "شارع 69", "طريق شوكين - حاروف" and "طريق شوكين
    حاروف" are the same name."""
    return re.sub(r"[^ء-ي0-9]", "", name.translate(str.maketrans("أإآىة", "ااايه")))


def classify_name(name):
    """('real' | 'generic' | 'none', old street number or None)."""
    if not isinstance(name, str) or not name.strip():
        return "none", None
    m = GENERIC_NUMBERED.match(name) or GENERIC_ORDINAL.match(name)
    if m:
        return "generic", int(m.group(1).translate(ARABIC_DIGITS))
    if normalize(name) in GENERIC_WORDS or GENERIC_LETTER.match(name) or is_code(name):
        return "generic", None
    return "real", None


class UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def node_degrees(all_ways):
    """Edge-ends per node over the whole drivable network (dead-end detection)."""
    deg = Counter()
    for nodes in all_ways:
        deg[nodes[0]] += 1
        deg[nodes[-1]] += 1
        for n in nodes[1:-1]:
            deg[n] += 2
    return deg


def build_edges(streets, communes, quarters, country):
    s = streets[streets.highway.isin(ADDRESSABLE)]
    s = s[~((s.highway == "service") & s.service.isin(SERVICE_SKIP))]
    s = s[(s["area"] != "yes") & ~s.junction.isin(["roundabout", "circular"])].to_crs(METRIC_CRS)
    mids = s.geometry.interpolate(0.5, normalized=True)
    shapely.prepare(country)
    s = s[shapely.contains_xy(country, mids.x, mids.y)]

    counts = Counter(n for nodes in s.nodes for n in nodes)
    rows = []
    for w in s.itertuples():
        coords = shapely.get_coordinates(w.geometry)
        nodes = list(w.nodes)
        cuts = [i for i, n in enumerate(nodes) if i == 0 or i == len(nodes) - 1 or counts[n] > 1]
        # A way tagged only "name:fr" or "name:en" is still a named street.
        name, name_fr, name_en = way_names(w)
        status, number = classify_name(name)
        for a, b in zip(cuts[:-1], cuts[1:]):
            seg = coords[a:b + 1]
            if len(seg) < 2 or np.allclose(seg[0], seg[-1]) and len(seg) == 2:
                continue
            rows.append((w.osm_id, a, b, nodes[a], nodes[b], w.highway, name, name_fr, name_en,
                         status, number, shapely.LineString(seg)))
    e = gpd.GeoDataFrame(rows, columns=["way_id", "i0", "i1", "u", "v", "highway", "name", "name_fr_osm",
                                        "name_en_osm", "name_status", "old_number", "geometry"], crs=METRIC_CRS)
    e = e[e.length > 0.5].reset_index(drop=True)
    e["length"] = e.length
    e["commune_id"], e["quarter_id"] = assign(e.geometry.interpolate(0.5, normalized=True), communes, quarters)
    # Group by the Arabic name each piece will be shown with, ignoring accents, spacing and
    # punctuation, so "Avenue Président…"/"Avenue President…" and "Route Harîssa"/"طريق حريصا"
    # (one street tagged differently on different ways) become one street.
    register_gazetteer(zip(communes.name_ar, communes.name_fr, communes.name_en))
    e["name_key"] = [name_key(n, en) for n, en in zip(e["name"], e["name_en_osm"])]
    # Carry main-road names along unnamed stretches first, so the grouping below sees them with
    # their own commune's keys.
    e = propagate_names(e)
    # Within a commune, pieces sharing their Arabic name or a specific French name are one street:
    # "Rue Jamil Houssami" on one way and "شارع جميل الحسامي" + name:fr on the next, or an avenue
    # whose name:fr is on some ways only.
    parent = {}

    def find(k):
        root = k
        while parent.setdefault(root, root) != root:
            root = parent[root]
        while parent[k] != root:
            parent[k], k = root, parent[k]
        return root

    # (An unnamed piece has no key at all: pandas would store it as NaN, which is truthy and would
    # chain every French-only name of the commune together.)
    for c, k, n, f in zip(e.commune_id, e.name_key, e["name"], e["name_fr_osm"]):
        fk = specific_fr_key(n, f) if isinstance(k, str) else None
        if fk:
            a, b = find((c, k)), find((c, fk))
            if a != b:
                parent[a] = b
    e["name_key"] = [find((c, k))[1] if isinstance(k, str) else None for c, k in zip(e.commune_id, e.name_key)]
    return e


def propagate_names(e):
    """Main roads in OSM often lose their name for a few segments (the Antelias-Bikfaya road is
    unnamed in several villages). An unnamed main-road edge that continues a named one straight
    through a junction takes its name, up to PROPAGATE_MAX_M from the last named piece."""
    main = e.highway.isin(MAIN_ROADS).values
    dir_u, dir_v = _end_directions(e)
    ends = defaultdict(list)
    for k in np.flatnonzero(main):
        ends[e.u.values[k]].append((k, 0))
        ends[e.v.values[k]].append((k, 1))
    status = e.name_status.values.copy()
    key = e.name_key.values.copy()
    source = np.arange(len(e))           # edge whose name each edge carries
    lengths = e["length"].values
    queue = deque((k, end, 0.0) for k in np.flatnonzero(main & (status == "real")) for end in (0, 1))
    while queue:
        k, end, run = queue.popleft()
        node = e.u.values[k] if end == 0 else e.v.values[k]
        incident = [(j, ej) for j, ej in ends[node] if j != k]
        if any(key[j] == key[k] for j, _ in incident):
            continue  # the named road already continues here
        vk = dir_u[k] if end == 0 else dir_v[k]
        best = None
        for j, ej in incident:
            vj = dir_u[j] if ej == 0 else dir_v[j]
            deflection = 180.0 - math.degrees(math.acos(float(np.clip(np.dot(vk, vj), -1, 1))))
            if deflection < PROPAGATE_DEFLECTION and (best is None or deflection < best[0]):
                best = (deflection, j, ej)
        if best is None or status[best[1]] != "none" or run + lengths[best[1]] > PROPAGATE_MAX_M:
            continue
        _, j, ej = best
        status[j], key[j], source[j] = "real", key[k], source[k]
        queue.append((j, 1 - ej, run + lengths[j]))
    took = np.flatnonzero(source != np.arange(len(e)))
    if len(took):
        cols = ["name", "name_fr_osm", "name_en_osm"]
        e.loc[e.index[took], cols] = e[cols].values[source[took]]
        e.loc[e.index[took], "name_status"] = "real"
        e.loc[e.index[took], "name_key"] = key[took]
    return e


def _end_directions(edges):
    """Unit vectors leaving each edge at its start (u) and at its end (v)."""
    g = edges.geometry.values
    L = edges["length"].values
    d = np.minimum(DIRECTION_SAMPLE_M, L)
    start, end = shapely.get_point(g, 0), shapely.get_point(g, -1)
    near_start = shapely.line_interpolate_point(g, d)
    near_end = shapely.line_interpolate_point(g, L - d)

    def unit(p, q):
        v = shapely.get_coordinates(q) - shapely.get_coordinates(p)
        n = np.linalg.norm(v, axis=1, keepdims=True)
        return v / np.where(n == 0, 1, n)

    return unit(start, near_start), unit(end, near_end)


def _strokes(edges, idx):
    """Chain unnamed edges (row positions `idx`) through junctions by best straight continuation."""
    sub = edges.iloc[idx]
    dir_u, dir_v = _end_directions(sub)
    ends = defaultdict(list)  # (node, commune) -> [(local edge pos, which end)]
    for k, (u, v, c) in enumerate(zip(sub.u.values, sub.v.values, sub.commune_id.values)):
        ends[(u, c)].append((k, 0))
        ends[(v, c)].append((k, 1))
    is_service = (sub.highway.values == "service")
    uf = UnionFind(len(sub))
    for incident in ends.values():
        if len(incident) < 2:
            continue
        cands = []
        for i in range(len(incident)):
            for j in range(i + 1, len(incident)):
                (a, ea), (b, eb) = incident[i], incident[j]
                if a == b:
                    continue
                va = dir_u[a] if ea == 0 else dir_v[a]
                vb = dir_u[b] if eb == 0 else dir_v[b]
                angle = math.degrees(math.acos(float(np.clip(np.dot(va, vb), -1, 1))))
                deflection = 180.0 - angle + (SERVICE_MISMATCH if is_service[a] != is_service[b] else 0)
                if deflection < MAX_DEFLECTION:
                    cands.append((deflection, i, j))
        used = set()
        for _, i, j in sorted(cands):
            if i in used or j in used:
                continue
            used.update((i, j))
            uf.union(incident[i][0], incident[j][0])
    return np.array([uf.find(k) for k in range(len(sub))])


def _bridge_components(G, xy, max_gap):
    """Connect pieces of a same-named street that are within max_gap, via virtual edges.
    Returns the list of node sets that remain separate streets."""
    comps = [list(c) for c in nx.connected_components(G)]
    if len(comps) == 1:
        return [set(comps[0])]
    trees = [cKDTree(np.array([xy[n] for n in c])) for c in comps]
    links = []
    for i in range(len(comps)):
        for j in range(i + 1, len(comps)):
            dist, k = trees[j].query(np.array([xy[n] for n in comps[i]]), distance_upper_bound=max_gap)
            m = int(np.argmin(dist))
            if np.isfinite(dist[m]):
                links.append((dist[m], comps[i][m], comps[j][k[m]]))
    uf = UnionFind(len(comps))
    pos = {n: ci for ci, c in enumerate(comps) for n in c}
    for dist, a, b in sorted(links):
        if uf.find(pos[a]) != uf.find(pos[b]):
            uf.union(pos[a], pos[b])
            G.add_edge(a, b, w=dist, eid=-1)
    groups = defaultdict(set)
    for ci, c in enumerate(comps):
        groups[uf.find(ci)].update(c)
    return list(groups.values())


def _spine(G, xy, edge_geoms, center):
    """Longest path through the street graph as one LineString, oriented to start at the end
    nearest the commune center (the French rule). Pure loops start at their node nearest it."""
    cx, cy = center
    dist_c = lambda n: (xy[n][0] - cx) ** 2 + (xy[n][1] - cy) ** 2
    if G.number_of_nodes() >= 3 and all(d == 2 for _, d in G.degree()):
        start = min(G.nodes, key=dist_c)
        path, prev, cur = [start], None, start
        for _ in range(G.number_of_nodes()):
            nxt = next(n for n in G.neighbors(cur) if n != prev)
            path.append(nxt)
            if nxt == start:
                break
            prev, cur = cur, nxt
    else:
        n0 = next(iter(G.nodes))
        far = nx.single_source_dijkstra_path_length(G, n0, weight="w")
        a = max(far, key=far.get)
        far, paths = nx.single_source_dijkstra(G, a, weight="w")
        b = max(far, key=far.get)
        path = paths[b]
        if dist_c(path[-1]) < dist_c(path[0]):
            path = path[::-1]
    coords = []
    for p, q in zip(path[:-1], path[1:]):
        eid = G.edges[p, q]["eid"]
        if eid < 0:
            seg = np.array([xy[p], xy[q]])
        else:
            seg = shapely.get_coordinates(edge_geoms[eid])
            if not np.allclose(seg[0], xy[p]):
                seg = seg[::-1]
        coords.append(seg if not coords else seg[1:])
    if not coords:
        return None, path
    return shapely.LineString(np.vstack(coords)), path


def build_streets(edges, communes, degree):
    """One row per logical street; also sets edges['street_id']."""
    centers = dict(zip(communes.commune_id, zip(communes.center.x, communes.center.y)))
    edges["group"] = None
    named = edges.name_status != "none"
    edges.loc[named, "group"] = "N|" + edges.loc[named, "commune_id"] + "|" + edges.loc[named, "name_key"]
    unnamed_idx = np.flatnonzero(~named.values)
    roots = _strokes(edges, unnamed_idx)
    edges.loc[edges.index[unnamed_idx], "group"] = "S|" + pd.Series(roots).astype(str).values

    xy = {}
    for u, v, g in zip(edges.u.values, edges.v.values, edges.geometry.values):
        c = shapely.get_coordinates(g)
        xy[u], xy[v] = tuple(c[0]), tuple(c[-1])

    edge_geoms = edges.geometry.values
    street_of_edge = np.full(len(edges), -1)
    rows = []
    for gkey, grp in edges.groupby("group", sort=False):
        G = nx.Graph()
        for eid, u, v, L in zip(grp.index.values, grp.u.values, grp.v.values, grp["length"].values):
            if u == v:
                continue
            if not G.has_edge(u, v) or G.edges[u, v]["w"] > L:
                G.add_edge(u, v, w=L, eid=eid)
        if G.number_of_nodes() == 0:
            continue
        gap = CODE_GAP_M if (grp.name_status == "generic").all() else \
            BRIDGE_GAP_M * (4 if grp.highway.isin(MAIN_ROADS).any() else 1)
        parts = _bridge_components(G, xy, gap) if gkey.startswith("N|") else \
            [set(c) for c in nx.connected_components(G)]
        commune = grp.commune_id.iloc[0]
        for nodes in parts:
            sub = G.subgraph(nodes).copy()
            spine, path = _spine(sub, xy, edge_geoms, centers[commune])
            if spine is None or spine.length < 1:
                continue
            members = grp[grp.u.isin(nodes) | grp.v.isin(nodes)]
            sid = len(rows)
            street_of_edge[members.index.values] = sid
            first = members.iloc[0]
            # One real name among the pieces makes it a real street; it is shown with an Arabic
            # `name` when a piece has one, the French/English tags (or a Latin `name`) otherwise.
            real = members[members.name_status == "real"]
            tagged = real if len(real) else members
            arabic = tagged["name"][tagged["name"].map(has_arabic)]
            latin = tagged["name"][tagged["name"].notna() & ~tagged["name"].map(has_arabic)]
            pick = lambda col: col.dropna().mode().iloc[0] if col.notna().any() else None
            osm_name = pick(arabic) or pick(tagged["name"])
            rows.append({
                "street_id": sid, "commune_id": commune,
                "quarter_id": members.quarter_id.mode().iloc[0] if members.quarter_id.notna().any() else None,
                "name_status": "real" if len(real) else first.name_status,
                "osm_name": osm_name,
                "osm_name_fr": _latin_tag(tagged, "name_fr_osm", osm_name, FR_HEAD)
                               or (pick(latin) if len(arabic) else None),
                "osm_name_en": _latin_tag(tagged, "name_en_osm", osm_name, EN_TAIL),
                "old_number": first.old_number,
                "highway": max(members.highway, key=CLASS_RANK.get),
                "length": float(members["length"].sum()),
                "spine_length": spine.length,
                "start_dead_end": degree[path[0]] == 1, "end_dead_end": degree[path[-1]] == 1,
                "start_node": path[0], "end_node": path[-1],
                "way_ids": sorted(set(members.way_id.tolist())),
                "spine": spine,
                "geometry": shapely.MultiLineString(list(members.geometry.values)),
            })
    edges["street_id"] = street_of_edge
    streets = gpd.GeoDataFrame(rows, geometry="geometry", crs=METRIC_CRS)
    streets["spine"] = gpd.GeoSeries(streets["spine"], crs=METRIC_CRS)
    return streets


FR_HEAD = re.compile(r"^(Rue|Route|Avenue|Boulevard|Impasse|Ruelle|Place|Autoroute|Chemin|Allée|Passage|Corniche)\b")
EN_TAIL = re.compile(r"\b(Street|Road|Avenue|Boulevard|Lane|Square|Highway|Way|Path|Corniche)$")


def _latin_tag(pieces, col, name, well_formed):
    """The name:fr or name:en of a street drawn as several OSM ways that disagree: the one naming
    what the Arabic name does ("Rue Alfred Naccache", not the "Rue Mar Dimitrious" also tagged on
    شارع ألفريد نقاش), then a well-formed one ("Rue Aref Naamani" over "Aref Naamani"), then the
    one on the longest stretch; the pieces carrying the street's Arabic name first."""
    have = pieces[pieces[col].notna()]
    if not len(have):
        return None
    same = have[have["name"] == name]
    lengths = (same if len(same) else have).groupby(col)["length"].sum()
    if len(lengths) == 1:
        return lengths.index[0]
    return max(lengths.index, key=lambda t: (has_arabic(name) and latin_matches(t, name), bool(well_formed.search(t)),
                                             lengths[t]))


def neighbor_communes(streets, edges):
    """Communes a street runs into at either end of its spine (for 'Route de X' names)."""
    by_node = defaultdict(set)
    for u, v, c in zip(edges.u.values, edges.v.values, edges.commune_id.values):
        by_node[u].add(c)
        by_node[v].add(c)
    out = []
    for s in streets.itertuples():
        out.append(sorted((by_node[s.start_node] | by_node[s.end_node]) - {s.commune_id}))
    return out


def orient_dead_ends(streets):
    """Number a dead-end from its open end (where you enter it), not from the commune center."""
    flip = streets.start_dead_end & ~streets.end_dead_end
    s = streets.copy()
    s.loc[flip, "spine"] = s.loc[flip, "spine"].reverse()
    s.loc[flip, ["start_node", "end_node"]] = s.loc[flip, ["end_node", "start_node"]].values
    s.loc[flip, ["start_dead_end", "end_dead_end"]] = [False, True]
    return s
