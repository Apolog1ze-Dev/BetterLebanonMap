"""Named places to search for: shops, schools, places of worship, pharmacies, offices, named buildings.

People in Lebanon give an address by what is nearby ("next to the pharmacy"), so the viewer finds
these by name and shows the address of the building each one is in or nearest to. They are read
from the OSM extract on their own, apart from the landmarks that name streets (extract.py), and
keep the names OSM has: nothing is spelled into a script OSM lacks.

viewer/data/pois.json: [[lon, lat, category, name_ar, name_fr, name_en], ...], names null where
OSM has none in that script.
"""

import json
import re
from pathlib import Path

import geopandas as gpd
import osmium
import shapely

from .localities import METRIC_CRS

ARABIC = re.compile(r"[؀-ۿ]")
CATEGORIES = ("place", "worship", "school", "health", "pharmacy", "fuel", "bank", "shop", "food", "hotel",
              "public", "leisure", "sight", "building", "office")
AMENITY = {
    "place_of_worship": "worship", "monastery": "worship",
    "school": "school", "university": "school", "college": "school", "kindergarten": "school",
    "language_school": "school", "music_school": "school", "driving_school": "school", "library": "school",
    "hospital": "health", "clinic": "health", "doctors": "health", "dentist": "health", "veterinary": "health",
    "pharmacy": "pharmacy", "fuel": "fuel", "bank": "bank", "bureau_de_change": "bank", "atm": "bank",
    "marketplace": "shop",
    "restaurant": "food", "cafe": "food", "fast_food": "food", "bar": "food", "pub": "food", "food_court": "food",
    "ice_cream": "food", "nightclub": "food",
    "townhall": "public", "police": "public", "fire_station": "public", "post_office": "public",
    "courthouse": "public", "community_centre": "public", "embassy": "public", "social_facility": "public",
    "bus_station": "public", "public_building": "public",
    "cinema": "leisure", "theatre": "leisure", "arts_centre": "leisure",
}
SKIP_AMENITY = {"parking", "parking_space", "parking_entrance", "bench", "waste_basket", "waste_disposal", "recycling",
                "vending_machine", "drinking_water", "toilets", "telephone", "shelter", "bicycle_parking", "fountain"}
TOURISM = {"hotel": "hotel", "guest_house": "hotel", "hostel": "hotel", "motel": "hotel", "chalet": "hotel",
           "apartment": "hotel", "camp_site": "hotel", "museum": "sight", "attraction": "sight", "viewpoint": "sight",
           "artwork": "sight", "gallery": "sight", "zoo": "leisure", "theme_park": "leisure", "picnic_site": "leisure"}


def category(tags):
    """The category of a named OSM object, or None when it is not a place people look for."""
    v = tags.get("amenity")
    if v:
        return None if v in SKIP_AMENITY else AMENITY.get(v, "place")
    if "shop" in tags:
        return "shop"
    v = tags.get("tourism")
    if v:
        return TOURISM.get(v, "place")
    if "healthcare" in tags:
        return "health"
    if "historic" in tags:
        return "sight"
    if "leisure" in tags:
        return "leisure"
    if "office" in tags:
        return "public" if tags["office"] in ("government", "diplomatic") else "office"
    if "craft" in tags:
        return "shop"
    if tags.get("building") not in (None, "no") and "highway" not in tags:
        return "building"
    return None


def names(tags):
    """[Arabic, French, English] as OSM has them; `name` counts for the script it is written in."""
    name = tags.get("name")
    ar = name if ARABIC.search(name) else None
    latin = None if ar else name
    return tags.get("name:ar") or ar, tags.get("name:fr") or latin, tags.get("name:en") or latin


def extract(pbf, out):
    """Named nodes and ways of the extract that are places -> GeoParquet; returns how many."""
    rows = []
    objects = osmium.FileProcessor(str(pbf), osmium.osm.NODE | osmium.osm.WAY).with_locations() \
        .with_filter(osmium.filter.KeyFilter("name"))
    for o in objects:
        cat = category(o.tags)
        if cat is None:
            continue
        if o.is_node():
            x, y = o.location.lon, o.location.lat
        else:   # a way stands where its nodes average out: near enough to find its building
            pts = [(n.lon, n.lat) for n in o.nodes if n.location.valid()]
            if not pts:
                continue
            x, y = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        ar, fr, en = names(o.tags)
        rows.append({"osm_type": "node" if o.is_node() else "way", "osm_id": o.id, "category": cat,
                     "name_ar": ar, "name_fr": fr, "name_en": en, "geometry": shapely.Point(x, y)})
    gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326").to_parquet(out)
    return len(rows)


def write_viewer(root, pois, country):
    """The places inside the country (the extract runs past the border), one per name and spot."""
    inside = pois.to_crs(METRIC_CRS).geometry.within(country).values
    p = pois[inside].drop_duplicates(["name_ar", "name_fr", "name_en", "geometry"])
    text = lambda v: v.strip() if isinstance(v, str) and v.strip() else None
    rows = [[round(g.x, 5), round(g.y, 5), CATEGORIES.index(c), text(ar), text(fr), text(en)]
            for g, c, ar, fr, en in zip(p.geometry.values, p.category.values, p.name_ar.values, p.name_fr.values,
                                        p.name_en.values)]
    Path(root, "pois.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
    return len(rows)
