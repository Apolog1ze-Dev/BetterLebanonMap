"""Second addresses: the other streets a building may be reached from.

A building takes its nearest street unless a driveway is known (access.py), and the map alone
cannot tell which street a house is really reached from: of the houses whose street the build
knows (a driveway drawn, mapped in OSM or seen in imagery), the nearest street is the right one
for 69%, and no rule on street and building geometry picks better. So the build does not pick. A
building whose street is not known gets an address on each street it could be reached from, and
all of them lead to it: its own on the nearest street, and an alias on

- up to MAX_ALIASES other streets, when it does not front its street (more than FRONTAGE_M from
  it): those at most EXTRA_M farther from its walls than the nearest one, within REACH_M;
- the other street of a corner, when it fronts its street: one within CORNER_M of its walls.

A street is left out when the straight way to it crosses another street (that is so for 0.2% of
the houses' known streets, and for a quarter of the others), or when it only comes that near where
it meets the building's own street. With these rules the known street is among a house's
addresses for 96% of the houses whose street the build knows, instead of 69%: `coverage` repeats
that check in every build.

An alias is numbered like any address, by the metres along its street and the side, and takes
the next free number of that side when a building of that street already has it: the buildings'
own numbers never move.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from . import addressing
from .access import FRONTAGE_M

EXTRA_M = 60.0        # a street this much farther than the nearest may still be the one a house is reached from
REACH_M = 130.0
CORNER_M = 10.0       # a building fronting its street with another street this close to its walls is on a corner
MAX_ALIASES = 3
STOP_SHORT_M = 1.5    # the way to a street is checked up to here, so the street itself and its junctions do not count
JUNCTION_M = 3.0      # a street's point this close to another street is their junction


def candidates(bld, edges, streets):
    """The other streets each building of `bld` may be reached from, taking its `street_id` and
    `dist_to_street` as the nearest street's: rows (b: position in bld, sid, d: metres from its walls)."""
    named = set(streets.street_id[streets.name_ar.notna()])
    e = edges[edges.street_id.isin(named)].reset_index(drop=True)
    lines, sids = e.geometry.values, e.street_id.values
    foot = bld.geometry.values
    tree = shapely.STRtree(lines)
    ib, ie = tree.query(foot, predicate="dwithin", distance=REACH_M)
    p = pd.DataFrame({"b": ib, "e": ie, "sid": sids[ie], "d": shapely.distance(foot[ib], lines[ie])})
    p = p.sort_values(["b", "d", "sid"]).drop_duplicates(["b", "sid"])
    p["nearest"] = p.groupby("b").d.transform("min")
    front = bld.dist_to_street.values[p.b.values] <= FRONTAGE_M
    p = p[(p.sid.values != bld.street_id.values[p.b.values])
          & np.where(front, p.d <= CORNER_M, p.d <= p.nearest + EXTRA_M)].reset_index(drop=True)

    way = shapely.shortest_line(foot[p.b.values], lines[p.e.values])
    ends = np.stack([shapely.get_coordinates(shapely.line_interpolate_point(way, x))
                     for x in (0.0, np.maximum(shapely.length(way) - STOP_SHORT_M, 0))], 1)
    iw, je = tree.query(shapely.linestrings(ends), predicate="intersects")
    crossed = np.zeros(len(p), dtype=bool)
    crossed[iw[sids[je] != p.sid.values[iw]]] = True
    # Nor a street that only comes this near where it meets the building's own street: from that
    # junction the building is reached along its own street.
    own = bld.street_id.values[p.b.values]
    has = own >= 0
    meets = np.zeros(len(p), dtype=bool)
    meets[has] = shapely.distance(shapely.points(ends[has, 1]), streets.set_index("street_id").geometry.loc[own[has]].values) < JUNCTION_M
    p = p[~crossed & ~meets]
    return p[p.groupby("b").cumcount() < MAX_ALIASES][["b", "sid", "d"]]


def find(bld, edges, streets):
    """bld: the addressed buildings, numbered. One row per alias: the building, the other street
    and the distance from its walls to it."""
    unknown = bld[(bld.access == "nearest").values]
    p = candidates(unknown, edges, streets)
    src = unknown.iloc[p.b.values]
    return gpd.GeoDataFrame({
        "osm_type": src.osm_type.values, "osm_id": src.osm_id.values, "point": src["point"].values,
        "street_id": p.sid.values, "dist_to_street": p.d.values,
        "primary_street_id": src.street_id.values, "primary_housenumber": src.housenumber.values,
    }, geometry="point", crs=bld.crs)


def coverage(known, nearest, edges, streets):
    """The rules tried on the buildings whose street is known (`known`, with that street as
    `street_id`), as if it were not: `nearest` holds the street_id and dist_to_street they had
    before their driveway was found. Returns how many there are, for how many the nearest street
    is the known one, and for how many the known one is the nearest or among the aliases."""
    guess = known.assign(street_id=nearest.street_id.loc[known.index].values,
                         dist_to_street=nearest.dist_to_street.loc[known.index].values)
    p = candidates(guess, edges, streets)
    right = guess.street_id.values == known.street_id.values
    right_alias = np.zeros(len(known), dtype=bool)
    right_alias[p.b.values[p.sid.values == known.street_id.values[p.b.values]]] = True
    return {"houses": len(known), "nearest_right": int(right.sum()), "among_addresses": int((right | right_alias).sum())}


def number(alias, bld, streets):
    """Numbers the aliases along their streets: the number its metres give, or the next free one of
    its side after the alias before it, skipping the numbers the street's own buildings have."""
    if not len(alias):
        return alias.assign(distance_along=[], side=[], ideal_number=[], housenumber=[])
    alias = addressing.positions(alias, streets)
    alias = alias.sort_values(["street_id", "side", "distance_along", "dist_to_street", "osm_id"])
    taken = set(zip(bld.street_id.values.tolist(), bld.housenumber.values.tolist()))
    numbers, last = [], (None, None, 0)
    for sid, side, ideal in zip(alias.street_id.values.tolist(), alias.side.values.tolist(), alias.ideal_number.values.tolist()):
        n = max(ideal, last[2] + 2) if last[:2] == (sid, side) else ideal
        while (sid, n) in taken:
            n += 2
        numbers.append(n)
        last = (sid, side, n)
    alias["housenumber"] = numbers
    return alias
