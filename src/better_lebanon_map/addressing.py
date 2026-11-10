"""Attach buildings to streets and give them French metric house numbers.

Numérotation métrique: a building's number is its distance in metres from the start of the
street (the end nearest the commune center), odd on the left and even on the right when
walking away from the start. Numbers on one side always increase along the street; two
buildings that would share a number get the next free one of the right parity.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from .localities import METRIC_CRS

NOT_ADDRESSABLE = {"greenhouse", "roof", "shed", "ruins", "garage", "garages", "carport", "hut",
                   "transformer_tower", "bunker", "storage_tank", "toilets", "kiosk", "service",
                   "construction", "container", "tent", "silo", "water_tower", "bridge", "no"}
MIN_FOOTPRINT_M2 = 20.0
MAX_DISTANCE_M = 100.0
SERVICE_PENALTY_M = 15.0   # a house this much closer to a service road than to a street still uses the street
MIN_SERVICE_STREET_M = 50.0


def addressable_buildings(buildings):
    b = buildings[~buildings.building.isin(NOT_ADDRESSABLE)].to_crs(METRIC_CRS)
    b = b[b.area >= MIN_FOOTPRINT_M2].copy()
    b["footprint_m2"] = b.area
    b["point"] = b.geometry.representative_point()
    return b.reset_index(drop=True)


def assign_streets(bld, edges, streets):
    """Nearest street within MAX_DISTANCE_M, preferring real streets over service roads; street_id
    -1 when none is that near (a driveway may still reach it, see access.attach)."""
    st = streets.set_index("street_id")
    e = edges[edges.street_id >= 0]
    hw = st.loc[e.street_id, "highway"].values
    long_enough = st.loc[e.street_id, "spine_length"].values >= MIN_SERVICE_STREET_M
    main = e[hw != "service"]
    serv = e[(hw == "service") & long_enough]
    pts = bld["point"].values

    def nearest(sub):
        tree = shapely.STRtree(sub.geometry.values)
        (ip, ie), d = tree.query_nearest(pts, max_distance=MAX_DISTANCE_M, return_distance=True, all_matches=False)
        sid = np.full(len(pts), -1)
        dist = np.full(len(pts), np.inf)
        sid[ip] = sub.street_id.values[ie]
        dist[ip] = d
        return sid, dist

    sid_m, d_m = nearest(main)
    sid_s, d_s = nearest(serv)
    use_service = d_s + SERVICE_PENALTY_M < d_m
    bld["street_id"] = np.where(use_service, sid_s, sid_m)
    bld["dist_to_street"] = np.where(use_service, d_s, d_m)
    return bld


def positions(bld, streets):
    """Where each building stands on its street: `distance_along` its spine in metres, the `side`,
    and `ideal_number`, the number those give (odd on the left, even on the right)."""
    st = streets.set_index("street_id")
    spines = st.loc[bld.street_id, "spine"].values
    L = shapely.length(spines)
    # A building reached by a driveway is numbered where the driveway leaves the street, on its side.
    pts = bld["anchor"].where(bld["anchor"].notna(), bld["point"]).values if "anchor" in bld else bld["point"].values
    d = shapely.line_locate_point(spines, pts)
    proj = shapely.line_interpolate_point(spines, d)
    a = shapely.get_coordinates(shapely.line_interpolate_point(spines, np.clip(d - 1, 0, L)))
    b = shapely.get_coordinates(shapely.line_interpolate_point(spines, np.clip(d + 1, 0, L)))
    p = shapely.get_coordinates(pts)
    o = shapely.get_coordinates(proj)
    tangent, offset = b - a, p - o
    cross = tangent[:, 0] * offset[:, 1] - tangent[:, 1] * offset[:, 0]

    bld["distance_along"] = d
    bld["side"] = np.where(cross > 0, "left", "right")
    ideal = np.rint(d).astype(int)
    want_odd = bld["side"].values == "left"
    ideal = np.where((ideal % 2 == 1) != want_odd, ideal + 1, ideal)
    ideal = np.maximum(ideal, np.where(want_odd, 1, 2))
    bld["ideal_number"] = ideal
    return bld


def metric_numbers(bld, streets):
    bld = positions(bld, streets)
    # Strictly increasing per side: n_i = max(ideal_i, n_{i-1} + 2) = 2i + cummax(ideal_j - 2j).
    bld = bld.sort_values(["street_id", "side", "distance_along", "dist_to_street"])
    i = bld.groupby(["street_id", "side"]).cumcount().values
    shifted = pd.Series(bld["ideal_number"].values - 2 * i, index=bld.index)
    bld["housenumber"] = 2 * i + shifted.groupby([bld.street_id, bld.side]).cummax().values
    return bld
