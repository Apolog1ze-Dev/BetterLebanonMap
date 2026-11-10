"""Run the whole pipeline: OSM extract -> named streets, metric house numbers, viewer data.

Usage: uv run python -I -m better_lebanon_map.pipeline [--pbf data/raw/lebanon-latest.osm.pbf]
       uv run python -I -m better_lebanon_map.pipeline --export-only   # reuse the last computed stage
"""

import argparse
import json
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import access, addressing, aliases, export, extract, lexicon, localities, naming, network, pois, routing, translit


def log(msg, t0=[time.time()]):
    print(f"[{time.time() - t0[0]:6.1f}s] {msg}", flush=True)


def compute(interim, load, communes, quarters, country, corrections, detected, judged, chosen):
    raw_streets, buildings, landmarks, places = load("streets"), load("buildings"), load("landmarks"), load("places")

    log("street network")
    degree = network.node_degrees(raw_streets[~raw_streets.highway.isin(["footway", "steps"])].nodes)
    edges = network.build_edges(raw_streets, communes, quarters, country)
    streets = network.build_streets(edges, communes, degree)
    log(f"  {len(edges):,} edges -> {len(streets):,} logical streets")

    log("attaching buildings to streets")
    bld = addressing.addressable_buildings(buildings)
    bld = addressing.assign_streets(bld, edges, streets)
    roads = access.load_detected(detected)
    nearest = bld[["street_id", "dist_to_street"]].copy()   # before any driveway, to try the aliases on (below)
    bld, reached = access.attach(bld, edges, streets, access.load_drawn(corrections), roads,
                                 raw_streets.to_crs(localities.METRIC_CRS),
                                 access.load_chosen(chosen) + access.load_judged(judged))
    bld = bld[bld.street_id >= 0].copy()
    log(f"  driveways: {reached['drawn']} drawn; streets chosen in the viewer: {reached['chosen']:,}; "
        f"judged streets: {reached['approved']:,} approved by a person, "
        f"{reached['judged']:,} by the model alone; {reached['mapped']:,} buildings by driveways, tracks, footways "
        f"and steps in OSM ({reached['mapped_changed_street']:,} change street, {reached['mapped_had_no_street']:,} "
        f"had none; {reached['mapped_lanes']:,} beside lanes keep the nearest); {reached['imagery']:,} buildings by "
        f"{reached['unmapped_tracks']:,} tracks seen in imagery and not in OSM ({reached['imagery_changed_street']:,} "
        f"change street), of {reached['detected_roads']:,} detected roads")
    streets["building_count"] = streets.street_id.map(bld.street_id.value_counts()).fillna(0).astype(int)
    streets = network.orient_dead_ends(streets)
    log(f"  {len(bld):,} buildings attached to a street")

    log("naming streets")
    neighbors = network.neighbor_communes(streets, edges)
    streets = naming.name_streets(streets, edges, landmarks, places, communes, quarters, neighbors)

    log("metric house numbers")
    bld = addressing.metric_numbers(bld, streets)
    bld = bld.rename(columns={"addr_housenumber": "old_housenumber", "addr_street": "old_street"})
    addresses = export.full_addresses(bld, streets, communes)

    log("second addresses on the other streets a building may be reached from")
    alt = export.full_addresses(aliases.number(aliases.find(bld, edges, streets), bld, streets), streets, communes)
    covered = aliases.coverage(bld[bld.access != "nearest"], nearest, edges, streets)
    log(f"  {len(alt):,} aliases for {len(alt.drop_duplicates(['osm_type', 'osm_id'])):,} buildings; of {covered['houses']:,} houses whose street "
        f"is known, the nearest street is that one for {covered['nearest_right']:,} and the nearest or an alias "
        f"for {covered['among_addresses']:,}")

    stage = interim / "stage"
    stage.mkdir(exist_ok=True)
    streets.to_parquet(stage / "streets.parquet")
    edges.to_parquet(stage / "edges.parquet")
    addresses.to_parquet(stage / "addresses.parquet")
    alt.to_parquet(stage / "aliases.parquet")
    (stage / "alias_coverage.json").write_text(json.dumps(covered))
    return streets, edges, addresses, alt, covered


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pbf", default="data/raw/lebanon-latest.osm.pbf")
    ap.add_argument("--interim", default="data/interim")
    ap.add_argument("--out", default="data/output")
    ap.add_argument("--viewer", default="viewer")
    ap.add_argument("--corrections", default="data/corrections/access.geojson")
    ap.add_argument("--detected", default="data/raw/ms_roads/lebanon.tsv")
    ap.add_argument("--judged", default="data/judge/judge.sqlite", help="the access judge's decisions (judge.py)")
    ap.add_argument("--chosen", default="data/corrections/streets.jsonl", help="streets chosen in the viewer (serve.py)")
    ap.add_argument("--re-extract", action="store_true")
    ap.add_argument("--export-only", action="store_true")
    args = ap.parse_args()
    interim = Path(args.interim)

    if args.re_extract or not (interim / "bilingual.parquet").exists():
        log("extracting OSM layers")
        extract.main(args.pbf, interim)
    if args.re_extract or not (interim / "pois.parquet").exists():
        log("extracting named places to search for")
        log(f"  {pois.extract(args.pbf, interim / 'pois.parquet'):,} places")
    load = lambda name: gpd.read_parquet(interim / f"{name}.parquet")
    admin = load("admin")

    log("learning spellings from OSM names written in both scripts")
    lex = lexicon.build(pd.read_parquet(interim / "bilingual.parquet"), interim / "lexicon.json")
    translit.register_lexicon(lex)
    log(f"  {len(lex['fr']):,} Arabic->French, {len(lex['en']):,} Arabic->English, {len(lex['ar']):,} Latin->Arabic words")

    log("communes and quarters")
    usage = localities.article_usage(pd.concat([load(n)[c] for n in ("streets", "landmarks", "places")
                                                for c in ("name", "name_ar")]))
    communes, quarters, areas = localities.build(admin, load("places"), usage=usage)
    country = admin[admin.admin_level == 2].to_crs(localities.METRIC_CRS).geometry.iloc[0]
    log(f"  {len(communes):,} cadastral communes, {len(areas['contested'])} contested areas")

    if args.export_only:
        stage = interim / "stage"
        streets, edges, addresses, alt = (gpd.read_parquet(stage / f"{n}.parquet")
                                          for n in ("streets", "edges", "addresses", "aliases"))
        covered = json.loads((stage / "alias_coverage.json").read_text())
        naming.register_places(communes, quarters, load("places"))   # place labels spelled as in a full run
    else:
        streets, edges, addresses, alt, covered = compute(interim, load, communes, quarters, country, args.corrections,
                                                          args.detected, args.judged, args.chosen)

    log("writing GIS outputs")
    export.write_gis(args.out, streets, addresses, alt, communes, areas)
    log("writing viewer data")
    export.write_viewer(args.viewer, streets, addresses, alt, communes, areas, load("places"), load("buildings"), quarters,
                        export.group_ways(load("streets"), edges, streets, communes, quarters))
    pois.write_viewer(Path(args.viewer) / "data", gpd.read_parquet(interim / "pois.parquet"), country)
    export.write_roads(Path(args.viewer) / "data", load("streets"), country)
    log("routing graph")
    translit.register_gazetteer(zip(communes.name_ar, communes.name_fr, communes.name_en))
    meta = routing.build(load("streets"), edges, country, Path(args.viewer) / "data")
    log(f"  {meta['nodes']:,} nodes, {meta['edges']:,} edges")

    named = streets[streets.name_ar.notna()]
    stats = {
        "osm_extract": Path(args.pbf).resolve().name,
        "communes": len(communes), "boundaries": "OCHA COD-AB v02 cadasters (CC BY-IGO)",
        "contested_areas": len(areas["contested"]),
        "logical_streets": len(streets), "named_streets": len(named),
        "name_source": named.name_source.value_counts().to_dict(),
        "names_needing_review": int(named.needs_review.sum()),
        "names_transcribed_from_latin": int(named.transcribed.sum()),
        "buildings_total": int(len(load("buildings"))), "buildings_addressed": len(addresses),
        "addresses_by_access": addresses.access.value_counts().to_dict() if "access" in addresses else {},
        "address_aliases": len(alt), "buildings_with_alias": len(alt.drop_duplicates(["osm_type", "osm_id"])),
        "houses_with_known_street": covered,
    }
    Path(args.out, "stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False))
    log(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
