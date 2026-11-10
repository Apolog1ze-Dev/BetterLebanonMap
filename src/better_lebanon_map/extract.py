"""Extract streets, buildings, landmarks and admin areas from an OSM .pbf into GeoParquet.

Usage: uv run python -I src/extract.py data/raw/lebanon-latest.osm.pbf data/interim
"""

import sys
from pathlib import Path

import re

import geopandas as gpd
import osmium
import pandas as pd
import shapely

# Roads that people live along. Motorways and links are kept for context but never numbered.
HIGHWAY_KEEP = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "pedestrian", "service", "road", "track", "steps", "footway",
}

# Things people already use as reference points when giving directions.
LANDMARK_KEYS = {
    "amenity": {
        "place_of_worship", "school", "university", "college", "hospital", "clinic",
        "townhall", "police", "fire_station", "post_office", "library", "marketplace",
        "fuel", "bank", "pharmacy", "kindergarten", "community_centre", "courthouse",
    },
    "leisure": {"park", "stadium", "sports_centre", "garden", "playground"},
    "historic": None,
    "tourism": {"museum", "hotel", "attraction", "viewpoint"},
    "shop": {"mall", "supermarket"},
    "public_transport": {"station"},
    "railway": {"station"},
    "natural": {"spring", "peak", "beach", "cave_entrance"},
    "waterway": {"river"},
    "man_made": {"lighthouse", "water_tower", "tower"},
    "office": {"government"},
}

ARABIC = re.compile(r"[\u0600-\u06FF]")
NAME_KEYS = ("name", "name:en", "name:fr", "name:ar", "alt_name", "old_name", "ref", "official_name")


def landmark_kind(tags):
    for key, values in LANDMARK_KEYS.items():
        v = tags.get(key)
        if v and (values is None or v in values):
            return f"{key}={v}"
    return None


def names(tags):
    return {k.replace(":", "_"): tags.get(k) for k in NAME_KEYS}


class Extractor(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.wkb = osmium.geom.WKBFactory()
        self.streets, self.buildings, self.landmarks, self.places, self.admin = [], [], [], [], []
        self.bilingual = []

    def _pair(self, tags):
        """Every object named in both scripts teaches how a word is spelled in the other one."""
        name = tags.get("name")
        if not name:
            return
        ar = tags.get("name:ar") or (name if ARABIC.search(name) else None)
        latin = name if not ARABIC.search(name) else None
        fr, en = tags.get("name:fr") or latin, tags.get("name:en") or latin
        if ar and (fr or en):
            self.bilingual.append({"ar": ar, "fr": fr, "en": en})

    def node(self, n):
        tags = n.tags
        if not tags:
            return
        self._pair(tags)
        if "place" in tags and "name" in tags:
            self.places.append({
                "osm_id": n.id, "place": tags["place"], **names(tags),
                "population": tags.get("population"),
                "geometry": shapely.Point(n.location.lon, n.location.lat),
            })
        kind = landmark_kind(tags)
        if kind and "name" in tags:
            self.landmarks.append({
                "osm_type": "node", "osm_id": n.id, "kind": kind, **names(tags),
                "religion": tags.get("religion"), "denomination": tags.get("denomination"),
                "geometry": shapely.Point(n.location.lon, n.location.lat),
            })

    def relation(self, r):
        self._pair(r.tags)

    def way(self, w):
        self._pair(w.tags)
        hw = w.tags.get("highway")
        if hw not in HIGHWAY_KEEP:
            return
        # Build the line from every node (not WKBFactory, which drops repeated locations)
        # so coordinates stay aligned with node ids for junction detection.
        try:
            coords = [(nd.lon, nd.lat) for nd in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(coords) < 2:
            return
        geom = shapely.LineString(coords)
        t = w.tags
        self.streets.append({
            "osm_id": w.id, "highway": hw, **names(t),
            "service": t.get("service"), "oneway": t.get("oneway"),
            "junction": t.get("junction"), "area": t.get("area"),
            "node_first": w.nodes[0].ref, "node_last": w.nodes[-1].ref,
            "nodes": [nd.ref for nd in w.nodes],
            "geometry": geom,
        })

    def area(self, a):
        t = a.tags
        is_building = "building" in t and t.get("building") not in ("no",)
        kind = landmark_kind(t)
        is_admin = t.get("boundary") == "administrative" and "admin_level" in t
        if not (is_building or (kind and "name" in t) or is_admin):
            return
        try:
            geom = shapely.from_wkb(self.wkb.create_multipolygon(a))
        except Exception:
            return
        osm_type = "way" if a.from_way() else "relation"
        osm_id = a.orig_id()
        if is_building:
            self.buildings.append({
                "osm_type": osm_type, "osm_id": osm_id, "building": t.get("building"),
                "name": t.get("name"), "levels": t.get("building:levels"),
                "addr_housenumber": t.get("addr:housenumber"), "addr_street": t.get("addr:street"),
                "geometry": geom,
            })
        if kind and "name" in t:
            self.landmarks.append({
                "osm_type": osm_type, "osm_id": osm_id, "kind": kind, **names(t),
                "religion": t.get("religion"), "denomination": t.get("denomination"),
                "geometry": geom.point_on_surface(),
            })
        if is_admin:
            self.admin.append({
                "osm_type": osm_type, "osm_id": osm_id, "admin_level": int(t["admin_level"])
                if t["admin_level"].isdigit() else None, **names(t), "geometry": geom,
            })


def main(pbf, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    h = Extractor()
    h.apply_file(pbf, locations=True)
    pd.DataFrame(h.bilingual).drop_duplicates().to_parquet(out / "bilingual.parquet")
    print(f"{'bilingual':10s} {len(h.bilingual):>8,d}")
    for layer in ("streets", "buildings", "landmarks", "places", "admin"):
        rows = getattr(h, layer)
        gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
        gdf.to_parquet(out / f"{layer}.parquet")
        print(f"{layer:10s} {len(gdf):>8,d}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
