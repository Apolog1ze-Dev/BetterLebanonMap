"""Write GIS outputs (GeoPackage, CSV) and the data files the web viewer loads.

Viewer files (all under viewer/data/):
  boundaries.json        governorates, districts and communes (rings delta-encoded at 1e-5 degree)
  places.json            village, hamlet and neighbourhood labels
  search.json            every named street, for the search box and for naming route steps
  pois.json              named places to search for (pois.py)
  roads.json             main roads of the whole country, drawn where the streets of a commune are not loaded
  stats.json             counts shown in the sidebar
  communes/<id>.json     streets and addresses of one commune, the aliases on its streets (aliases.py), and
                         its other roads, drawn but not named: motorways, ramps, roundabouts, tracks, paths
  buildings/<id>.json    building footprints of one commune (delta-encoded at 1e-6 degree)
  route.bin, route.json  routing graph (see routing.py)
"""

import json
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from shapely.ops import substring

from .access import KINDS
from .localities import CITY_GROUPS, METRIC_CRS, _key, _names, assign

SOURCE_CODE = {"osm": 0, "landmark": 1, "destination": 2, "systematic": 3, "theme": 4, "branch": 5, "place": 6}
KIND_CODE = {"rue": 0, "route": 1, "impasse": 2, "passage": 3, "chemin": 4, "allee": 5}
COMMUNE_KIND = {"city": 0, "town": 1, "village": 2, "quarter": 3}
PLACE_TYPE = {"city": 0, "town": 1, "village": 2, "suburb": 3, "quarter": 3, "neighbourhood": 4, "hamlet": 4,
              "locality": 5}
WORSHIP = {"church", "mosque", "chapel", "cathedral", "temple", "religious", "synagogue", "shrine", "monastery"}
MINOR = {"greenhouse", "shed", "roof", "ruins", "garage", "garages", "carport", "hut", "construction", "container",
         "storage_tank", "kiosk", "service", "transformer_tower", "bunker", "toilets", "tent", "silo", "bridge"}
PUBLIC = {"school", "hospital", "university", "college", "kindergarten", "government", "public", "civic",
          "train_station", "transportation", "stadium", "fire_station", "sports_hall", "museum", "townhall"}
TO_WGS = Transformer.from_crs(METRIC_CRS, "EPSG:4326", always_xy=True)


def full_addresses(addr, streets, communes):
    st = streets.set_index("street_id")
    cm = communes.set_index("commune_id")
    a = addr.join(st[["name_ar", "name_fr", "name_en", "name_source", "commune_id"]], on="street_id")
    a = a.join(cm[["name_ar", "name_fr", "name_en", "district_fr"]].add_prefix("commune_"), on="commune_id")
    n = a.housenumber.astype(str)
    a["address_fr"] = n + " " + a.name_fr + ", " + a.commune_name_fr
    a["address_en"] = n + " " + a.name_en + ", " + a.commune_name_en
    a["address_ar"] = a.name_ar + "، رقم " + n + "، " + a.commune_name_ar
    return a


def write_gis(out_dir, streets, addresses, alt, communes, areas):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    s = streets[streets.name_ar.notna()].drop(columns=["spine"]).copy()
    s["way_ids"] = s.way_ids.map(lambda w: ",".join(map(str, w)))
    s.to_crs(4326).to_file(out / "streets.gpkg", layer="streets", driver="GPKG")
    a = addresses.drop(columns=["geometry", "anchor", "access_path"], errors="ignore")
    a = a.set_geometry("point", crs=METRIC_CRS).to_crs(4326).rename_geometry("geometry")
    a.to_file(out / "addresses.gpkg", layer="addresses", driver="GPKG")
    if "access_path" in addresses:   # driveways drawn or seen in imagery, from the street to the building
        ap = addresses[addresses.access_path.notna()]
        gpd.GeoDataFrame(ap[["osm_type", "osm_id", "access", "street_id"]], geometry=ap.access_path.values,
                         crs=METRIC_CRS).to_crs(4326).to_file(out / "addresses.gpkg", layer="access_paths", driver="GPKG")
    cols = ["osm_type", "osm_id", "housenumber", "side", "address_fr", "address_en", "address_ar",
            "name_source", "commune_id", "old_housenumber", "old_street", "access"]
    pd.DataFrame(a[cols]).assign(lon=a.geometry.x.round(6), lat=a.geometry.y.round(6)).to_csv(
        out / "addresses.csv", index=False)
    # Second addresses: the same buildings on the other streets they may be reached from (aliases.py).
    b = alt.set_geometry("point", crs=METRIC_CRS).to_crs(4326).rename_geometry("geometry")
    b = b.merge(addresses[["osm_type", "osm_id", "address_fr"]].rename(columns={"address_fr": "primary_address_fr"}),
                on=["osm_type", "osm_id"], how="left")
    b["dist_to_street"] = b.dist_to_street.round(1)
    cols = ["osm_type", "osm_id", "housenumber", "side", "address_fr", "address_en", "address_ar", "commune_id",
            "dist_to_street", "primary_address_fr"]
    b[[*cols, "geometry"]].to_file(out / "addresses.gpkg", layer="aliases", driver="GPKG")
    pd.DataFrame(b[cols]).assign(lon=b.geometry.x.round(6), lat=b.geometry.y.round(6)).to_csv(
        out / "address_aliases.csv", index=False)
    keep = ["commune_id", "pid", "name_ar", "name_fr", "name_en", "kind", "source", "district_fr", "governorate_fr",
            "area_km2", "contested_km2", "geometry"]
    gpk = out / "boundaries.gpkg"
    gpk.unlink(missing_ok=True)
    communes[keep].rename(columns={"pid": "ocha_pcode"}).to_crs(4326).to_file(gpk, layer="communes", driver="GPKG")
    for layer in ("districts", "governorates"):
        areas[layer][["name_ar", "name_fr", "name_en", "geometry"]].to_crs(4326).to_file(gpk, layer=layer, driver="GPKG")
    areas["contested"].to_crs(4326).to_file(gpk, layer="contested", driver="GPKG")
    (out / "communes.gpkg").unlink(missing_ok=True)


def _rings(geom, scale=1e5):
    """Polygon/MultiPolygon (WGS84) -> [[ring, ...], ...] with rings as delta-encoded int lists."""
    out = []
    for poly in shapely.get_parts(geom):
        if poly.geom_type != "Polygon" or poly.is_empty:
            continue
        rings = []
        for ring in [poly.exterior, *poly.interiors]:
            q = np.round(shapely.get_coordinates(ring)[:-1] * scale).astype(np.int64)
            if len(q) < 3:
                continue
            d = np.vstack([q[:1], np.diff(q, axis=0)])
            rings.append(d.ravel().tolist())
        if rings:
            out.append(rings)
    return out


def _simplify_coverage(geoms, tolerance):
    try:
        return shapely.coverage_simplify(geoms, tolerance)
    except Exception:
        return shapely.simplify(geoms, tolerance, preserve_topology=True)


def _write(path, doc):
    path.write_text(json.dumps(doc, ensure_ascii=False, allow_nan=False, separators=(",", ":")))


def _lines_lonlat(geom):
    return [np.round(shapely.get_coordinates(g), 5).tolist() for g in shapely.get_parts(geom)]


def _str(v):
    return v if isinstance(v, str) else None


def write_boundaries(root, communes, areas, counts):
    doc = {}
    for key, tol in (("governorates", 120), ("districts", 60)):
        df = areas[key]
        geoms = gpd.GeoSeries(_simplify_coverage(df.geometry.values, tol), crs=METRIC_CRS).to_crs(4326)
        labels = gpd.GeoSeries(df.geometry.representative_point(), crs=METRIC_CRS).to_crs(4326)
        doc[key] = [{"ar": r.name_ar, "fr": r.name_fr, "en": r.name_en,
                     "label": [round(p.x, 5), round(p.y, 5)], "p": _rings(g)}
                    for r, g, p in zip(df.itertuples(), geoms.values, labels.values)]
    geoms = gpd.GeoSeries(_simplify_coverage(communes.geometry.values, 12), crs=METRIC_CRS).to_crs(4326)
    centers = gpd.GeoSeries(communes.center.values, crs=METRIC_CRS).to_crs(4326)
    contested = areas["contested"].geometry.simplify(8).to_crs(4326)
    doc["contested"] = [{"p": _rings(g)} for g in contested.values]
    wgs = communes.to_crs(4326)
    doc["communes"] = []
    for i, r in enumerate(communes.itertuples()):
        g = geoms.values[i]
        minx, miny, maxx, maxy = shapely.bounds(wgs.geometry.values[i])
        n_streets, n_addr = counts.get(r.commune_id, (0, 0))
        pop = pd.to_numeric(pd.Series([r.population]), errors="coerce").iloc[0]
        doc["communes"].append({
            "id": r.commune_id, "ar": r.name_ar, "fr": r.name_fr, "en": r.name_en,
            "kind": COMMUNE_KIND[r.kind], "est": int(r.source == "estimated"),
            "cont": round(float(r.contested_km2), 2),
            "d": int(r.district_idx), "g": int(r.governorate_idx),
            "label": [round(centers.values[i].x, 5), round(centers.values[i].y, 5)],
            "bbox": [round(minx, 5), round(miny, 5), round(maxx, 5), round(maxy, 5)],
            "streets": n_streets, "addr": n_addr, "pop": None if pd.isna(pop) else int(pop),
            "area": round(r.area_km2, 2), "p": _rings(g),
        })
    _write(root / "boundaries.json", doc)


def write_places(root, places, communes):
    pl = places[places.place.isin(PLACE_TYPE)].to_crs(METRIC_CRS).reset_index(drop=True)
    names = _names(pl)
    # A city spread over several cadasters is labelled as its roads name it ("Saïda", not OSM's "Sidon").
    city = {_key(ar): (fr, en) for ar, fr, en in CITY_GROUPS.values()}
    for i, k in names.name_ar.map(_key).items():
        if k in city:
            names.loc[i, ["name_fr", "name_en"]] = city[k]
    # A village node that is a commune's center under the same name is already that commune's
    # label. A city spread over several cadasters (Beirut, Tripoli) keeps its own label.
    centers = shapely.STRtree(communes.center.values)
    (ip, ic), d = centers.query_nearest(pl.geometry.values, return_distance=True, all_matches=False)
    duplicate = np.zeros(len(pl), dtype=bool)
    for i, c, dist in zip(ip, ic, d):
        if dist <= 1:
            row = communes.iloc[c]
            duplicate[i] = _key(names.name_ar.iat[i]) == _key(row.name_ar) or \
                _key(names.name_fr.iat[i]) == _key(row.name_fr)
    # So is any place named like the commune it lies in, which would show twice in two spellings
    # ("Achrafieh" from OSM beside the commune's "Achrafié").
    inside = gpd.sjoin(gpd.GeoDataFrame({"i": range(len(pl))}, geometry=pl.geometry.values, crs=METRIC_CRS),
                       communes[["name_ar", "geometry"]], predicate="within", how="inner")
    own = inside.name_ar.str.replace(r"\s*\([^)]*\)$", "", regex=True).map(_key).values
    duplicate[inside.i.values[own == names.name_ar.map(_key).values[inside.i.values]]] = True
    pl, names = pl[~duplicate].to_crs(4326), names[~duplicate]
    _write(root / "places.json", [
        [round(p.x, 5), round(p.y, 5), PLACE_TYPE[t], n.name_ar, n.name_fr, n.name_en]
        for p, t, n in zip(pl.geometry.values, pl.place.values, names.itertuples())])


ROAD_CLASS = {"motorway": 0, "trunk": 0, "primary": 1, "secondary": 2, "tertiary": 3}


def write_roads(root, ways, country):
    """The main roads inside the country, for the viewer's own base map (no tiles) below the zoom
    where streets load: [[class (0 motorway and trunk ... 3 tertiary), [[lon, lat], ...]], ...],
    the ways of a class joined end to end and simplified to 15 m."""
    w = ways[ways.highway.str.replace("_link", "").isin(ROAD_CLASS)].to_crs(METRIC_CRS)
    w = w[w.intersects(country)]
    rows = []
    for cls, group in w.groupby(w.highway.str.replace("_link", "").map(ROAD_CLASS)):
        lines = shapely.get_parts(shapely.line_merge(shapely.multilinestrings(group.geometry.values)))
        lines = gpd.GeoSeries(shapely.simplify(lines, 15.0), crs=METRIC_CRS).to_crs(4326).values
        rows += [[int(cls), np.round(shapely.get_coordinates(g), 5).tolist()] for g in lines]
    _write(root / "roads.json", rows)
    return len(rows)


PIECE_M = 300.0   # a long way is cut into pieces this long, each listed with the commune it lies in


def group_ways(ways, edges, streets, communes, quarters):
    """Every road OSM draws that is not a named street, for the viewer's own base map to show at
    full detail: the ways the addressing network leaves out (motorways and ramps, roundabouts,
    tracks and paths) and the stretches of that network that got no name (short connectors,
    yards). {commune_id: [[highway, [line, ...]], ...]}, the lines of a class joined end to end
    and simplified to 1 m, as [[lon, lat], ...]."""
    named = set(streets.street_id[streets.name_ar.notna()])
    plain = edges.loc[~edges.street_id.isin(named), ["highway", "geometry"]]
    other = ways[~ways.osm_id.isin(edges.way_id) & (ways["area"] != "yes")].to_crs(METRIC_CRS)
    highway = np.concatenate([plain.highway.values, other.highway.values])
    lines = np.concatenate([plain.geometry.values, other.geometry.values])
    # A commune's file is loaded when the commune is in view: a motorway 2 km long must not hang
    # on the one commune its middle lies in.
    parts, kind = [], []
    for line, length, hw in zip(lines, shapely.length(lines), highway):
        n = max(1, int(np.ceil(length / PIECE_M)))
        parts += [line] if n == 1 else [substring(line, k * length / n, (k + 1) * length / n) for k in range(n)]
        kind += [hw] * n
    parts = gpd.GeoSeries(parts, crs=METRIC_CRS)
    where, _ = assign(parts.interpolate(0.5, normalized=True), communes, quarters)
    both = pd.DataFrame({"highway": kind, "commune_id": where.values, "geometry": parts.values}).dropna(subset=["commune_id"])
    out = {}
    for (cid, hw), group in both.groupby(["commune_id", "highway"]):
        merged = shapely.get_parts(shapely.line_merge(shapely.multilinestrings(group.geometry.values)))
        coords, line = shapely.get_coordinates(shapely.simplify(merged, 1.0), return_index=True)
        lon, lat = TO_WGS.transform(coords[:, 0], coords[:, 1])
        lonlat = np.round(np.column_stack([lon, lat]), 5)
        out.setdefault(cid, []).append([hw, [part.tolist() for part in np.split(lonlat, np.flatnonzero(np.diff(line)) + 1)]])
    return out


def group_buildings(buildings, addresses, communes, quarters):
    """Footprints grouped by the commune whose address list they point into:
    {commune_id: [(building key, category, delta-encoded ring), ...]}."""
    b = buildings.to_crs(METRIC_CRS)
    b = b[~b.geometry.is_empty].reset_index(drop=True)
    parts, idx = shapely.get_parts(b.geometry.values, return_index=True)
    best = pd.Series(shapely.area(parts)).groupby(idx).idxmax().values
    poly = shapely.simplify(parts[best], 0.5)
    coords, owner = shapely.get_coordinates(shapely.get_exterior_ring(poly), return_index=True)
    lon, lat = TO_WGS.transform(coords[:, 0], coords[:, 1])
    q = np.column_stack([np.round(lon * 1e6), np.round(lat * 1e6)]).astype(np.int64)

    keys = (b.osm_type.str[0] + b.osm_id.astype(str)).values
    akeys = (addresses.osm_type.str[0] + addresses.osm_id.astype(str)).values
    by_address = pd.Series(addresses.commune_id.values, index=akeys).reindex(keys).values
    by_location, _ = assign(gpd.GeoSeries(poly, crs=METRIC_CRS).representative_point(), communes, quarters)
    commune = np.where(pd.isna(by_address), by_location.values, by_address)
    cat = np.select([b.building.isin(WORSHIP), b.building.isin(MINOR), b.building.isin(PUBLIC)], [1, 2, 3], 0)

    starts = np.searchsorted(owner, np.arange(len(b)))
    ends = np.searchsorted(owner, np.arange(len(b)), side="right")
    out = {}
    for i, (s0, s1) in enumerate(zip(starts, ends)):
        pts = q[s0:s1 - 1]  # drop the closing point
        if len(pts) < 3:
            continue
        d = np.vstack([pts[:1], np.diff(pts, axis=0)]).ravel().tolist()
        out.setdefault(commune[i], []).append((keys[i], int(cat[i]), d))
    return out


def write_viewer(viewer_dir, streets, addresses, alt, communes, areas, places, buildings, quarters, ways):
    root = Path(viewer_dir) / "data"
    for sub in ("communes", "buildings"):
        shutil.rmtree(root / sub, ignore_errors=True)
        (root / sub).mkdir(parents=True)
    (root / "index.json").unlink(missing_ok=True)

    s = streets[streets.name_ar.notna()].copy()
    # The line house numbers are measured along, for the viewer to place a number no building has. It
    # is written only where the street's pieces do not join into that one line (branches, gaps, loops).
    merged = shapely.line_merge(s.geometry.values)
    plain = (shapely.get_type_id(merged) == 1) & ~shapely.is_closed(merged) & \
        (np.abs(shapely.length(merged) - s.spine_length.values) < 1)
    spines = gpd.GeoSeries(shapely.simplify(s.spine.values, 1.0), crs=METRIC_CRS).to_crs(4326).values
    s["spine_lonlat"] = [None if p else np.round(shapely.get_coordinates(g), 5).tolist() for p, g in zip(plain, spines)]
    s["geometry"] = s.geometry.simplify(1.0)
    s = s.to_crs(4326)
    s["start"] = gpd.GeoSeries(shapely.get_point(s.spine.values, 0), crs=METRIC_CRS).to_crs(4326).values
    if "access" not in addresses:   # a stage computed before access paths existed
        addresses = addresses.assign(access="nearest", access_path=None)
    a = addresses.set_geometry("point", crs=METRIC_CRS).to_crs(4326)
    paths = gpd.GeoSeries(addresses.access_path.values, index=a.index, crs=METRIC_CRS).to_crs(4326)
    a["access_lonlat"] = [None if p is None else np.round(shapely.get_coordinates(p), 6).tolist() for p in paths.values]
    footprints = group_buildings(buildings, addresses, communes, quarters)
    # Aliases: with the building's own address, [street id, number] of each; and with the commune of
    # the alias's street, [number, street id, building key, the commune its building is listed in].
    alt = alt.assign(key=(alt.osm_type.str[0] + alt.osm_id.astype(str)).values)
    home = pd.Series(addresses.commune_id.values, index=(addresses.osm_type.str[0] + addresses.osm_id.astype(str)).values)
    alt["home"] = home.reindex(alt.key.values).values
    also = {}
    for k, sid, n in zip(alt.key.values, alt.street_id.values, alt.housenumber.values):
        also.setdefault(k, []).append([int(sid), int(n)])
    alt_by = dict(tuple(alt.groupby("commune_id")))

    cidx = {cid: i for i, cid in enumerate(communes.commune_id)}
    s_by = dict(tuple(s.groupby("commune_id")))
    a_by = dict(tuple(a.groupby("commune_id")))
    counts, search = {}, []
    for cid in communes.commune_id:
        cs, ca = s_by.get(cid), a_by.get(cid)
        addr_rows, addr_pos = [], {}
        if ca is not None:
            for k, (p, n, sid, side, t, oid, kind, path) in enumerate(zip(
                    ca.point.values, ca.housenumber.values, ca.street_id.values, ca.side.values,
                    ca.osm_type.values, ca.osm_id.values, ca.access.values, ca.access_lonlat.values)):
                row = [round(p.x, 6), round(p.y, 6), int(n), int(sid), 0 if side == "left" else 1, f"{t[0]}{oid}"]
                others = also.get(f"{t[0]}{oid}")
                if path is not None:   # reached by a driveway: [its access.KINDS index, path from the street]
                    row.append([KINDS.index(kind), path])
                elif others:
                    row.append(0)
                if others:
                    row.append(others)
                addr_rows.append(row)
                addr_pos[f"{t[0]}{oid}"] = k
        street_rows = []
        if cs is not None:
            for r in cs.itertuples():
                street_rows.append([
                    int(r.street_id), r.name_ar, r.name_fr, r.name_en, SOURCE_CODE[r.name_source],
                    _str(r.old_name), 1 if r.needs_review else 2 if r.transcribed else 0, r.highway, KIND_CODE.get(r.kind, 0),
                    _str(r.name_ref), [round(r.start.x, 5), round(r.start.y, 5)], _lines_lonlat(r.geometry),
                    round(float(r.spine_length)),   # house numbers are metres along this length
                    *([r.spine_lonlat] if r.spine_lonlat is not None else [])])
                search.append([int(r.street_id), cidx[cid], r.name_ar, r.name_fr, r.name_en, SOURCE_CODE[r.name_source]])
        counts[cid] = (len(street_rows), len(addr_rows))
        ca = alt_by.get(cid)
        alt_rows = [] if ca is None else [
            [int(n), int(sid), k, *([h] if h != cid else [])]
            for n, sid, k, h in zip(ca.housenumber.values, ca.street_id.values, ca.key.values, ca.home.values)]
        if street_rows or cid in ways:
            _write(root / "communes" / f"{cid}.json", {"id": cid, "streets": street_rows, "addr": addr_rows,
                                                       "alt": alt_rows, "ways": ways.get(cid, [])})
        fp = footprints.get(cid)
        if fp:
            _write(root / "buildings" / f"{cid}.json",
                   [[addr_pos.get(k, -1), cat, d] for k, cat, d in fp])

    write_boundaries(root, communes, areas, counts)
    write_places(root, places, communes)
    _write(root / "search.json", search)
    named = streets[streets.name_ar.notna()]
    _write(root / "stats.json", {
        "communes": len(communes), "contested_areas": len(areas["contested"]),
        "streets": len(named), "addresses": len(addresses), "aliases": len(alt), "buildings": len(buildings),
        "sources": {k: int(v) for k, v in named.name_source.value_counts().items()},
        "review": int(named.needs_review.sum()), "transcribed": int(named.transcribed.sum()),
    })
