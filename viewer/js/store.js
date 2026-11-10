// Loads and caches the viewer data (see src/better_lebanon_map/export.py for the formats).

import { chainParts, decodePolys, decodeRing, fetchJSON, haversine } from "./util.js";

export const SRC = ["osm", "landmark", "destination", "systematic", "theme", "branch", "place"];
export const KIND = ["rue", "route", "impasse", "passage"];

export const store = {
  site: {},              // site.json of a published copy: {repo: "owner/name", bases: [...]} (publish.py)
  stats: null,
  governorates: [], districts: [], communes: [], places: [], contested: [],
  communeById: new Map(),
  loaded: new Map(),     // commune id -> {streets, streetById, addr, addrByKey}
  buildings: new Map(),  // commune id -> [{addr, cat, ring}]
  search: null,          // [{sid, c, names, src}]
  streetNames: null,     // sid -> search row
  pois: null,            // [{lon, lat, cat, names}] named places to search for
};

const pending = new Map();
const once = (key, fn) => {
  if (!pending.has(key)) pending.set(key, fn().catch(e => { pending.delete(key); throw e; }));
  return pending.get(key);
};

export async function loadBase() {
  const [b, places, stats, site] = await Promise.all([
    fetchJSON("data/boundaries.json"), fetchJSON("data/places.json"), fetchJSON("data/stats.json"),
    fetchJSON("site.json").catch(() => ({}))]);
  store.stats = stats;
  store.site = site;
  for (const key of ["governorates", "districts"]) {
    store[key] = b[key].map(a => ({ ...a, polys: decodePolys(a.p) }));
  }
  store.communes = b.communes.map((c, i) => ({
    ...c, idx: i, polys: decodePolys(c.p), osmPolys: c.osm ? decodePolys(c.osm) : null,
  }));
  store.communes.forEach(c => { delete c.p; delete c.osm; store.communeById.set(c.id, c); });
  store.contested = (b.contested ?? []).map(a => decodePolys(a.p));
  store.places = places.map(([lon, lat, type, ar, fr, en]) => ({ lon, lat, type, names: [ar, fr, en] }));
}

export const communeAt = (lat, lng) => {
  for (const c of store.communes) {
    const [x0, y0, x1, y1] = c.bbox;
    if (lng < x0 || lng > x1 || lat < y0 || lat > y1) continue;
    if (inside(c.polys, lat, lng)) return c;
  }
  return null;
};

function inside(polys, lat, lng) {
  for (const rings of polys) {
    let hit = false;
    for (const ring of rings) {
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const [yi, xi] = ring[i], [yj, xj] = ring[j];
        if ((yi > lat) !== (yj > lat) && lng < (xj - xi) * (lat - yi) / (yj - yi) + xi) hit = !hit;
      }
    }
    if (hit) return true;
  }
  return false;
}

export function loadCommune(id) {
  if (store.loaded.has(id)) return Promise.resolve(store.loaded.get(id));
  return once(`c:${id}`, async () => {
    const doc = await fetchJSON(`data/communes/${id}.json`).catch(() => ({ streets: [], addr: [] }));
    const streets = doc.streets.map(([sid, ar, fr, en, src, old, review, highway, kind, ref, start, parts, measured, spine]) => {
      // The length house numbers are measured along (gaps between the street's pieces included).
      let len = measured ?? 0;
      if (measured == null) for (const p of parts) for (let i = 1; i < p.length; i++) len += haversine(p[i - 1][1], p[i - 1][0], p[i][1], p[i][0]);
      // review: 1 = spelling generated letter by letter, 2 = Arabic transcribed from a Latin-only OSM name
      // spine: the line numbers are measured along, given when the pieces do not join into it (see spineOf).
      // alts: the aliases on this street, addresses of buildings that have their own on another street.
      return { sid, names: [ar, fr, en], src, old, review: review ?? 0, highway, kind, ref, start, parts, len, spine,
        commune: id, addrs: [], alts: [] };
    });
    const streetById = new Map(streets.map(s => [s.sid, s]));
    // access: [1 drawn | 2 seen in imagery | 3 judged | 4 approved | 5 mapped in OSM | 6 chosen in the viewer,
    // [[lon, lat], ...] from the street] for a house reached by a driveway; also: [[street id, number], ...],
    // its aliases on the other streets it may be reached from
    const addr = doc.addr.map(([lon, lat, num, sid, side, key, access, also], i) =>
      ({ i, lon, lat, num, sid, side, key, access: access || null, also: also ?? [], commune: id }));
    const addrByKey = new Map();
    for (const a of addr) {
      addrByKey.set(a.key, a);
      streetById.get(a.sid)?.addrs.push(a);
    }
    // home: the commune whose list holds the building
    for (const [num, sid, key, home] of doc.alt ?? []) streetById.get(sid)?.alts.push({ num, sid, key, home: home ?? id });
    for (const s of streets) {
      const odd = s.addrs.filter(a => a.side === 0).map(a => a.num), even = s.addrs.filter(a => a.side === 1).map(a => a.num);
      s.odd = odd.length ? [Math.min(...odd), Math.max(...odd)] : null;
      s.even = even.length ? [Math.min(...even), Math.max(...even)] : null;
    }
    // ways: the commune's other roads, [[highway, [[[lon, lat], ...], ...]], ...]: drawn, never selected
    const data = { id, streets, streetById, addr, addrByKey, ways: doc.ways ?? [] };
    store.loaded.set(id, data);
    return data;
  });
}

export function loadBuildings(id) {
  if (store.buildings.has(id)) return Promise.resolve(store.buildings.get(id));
  return once(`b:${id}`, async () => {
    const rows = await fetchJSON(`data/buildings/${id}.json`).catch(() => []);
    const list = rows.map(([addr, cat, flat]) => ({ addr, cat, ring: decodeRing(flat, 1e6) }));
    store.buildings.set(id, list);
    return list;
  });
}

export function loadSearch() {
  if (store.search) return Promise.resolve(store.search);
  return once("search", async () => {
    const rows = await fetchJSON("data/search.json");
    store.search = rows.map(([sid, c, ar, fr, en, src]) => ({ sid, c, names: [ar, fr, en], src }));
    store.streetNames = new Map(store.search.map(r => [r.sid, r]));
    return store.search;
  });
}

export function loadPois() {
  if (store.pois) return Promise.resolve(store.pois);
  return once("pois", async () => {
    const rows = await fetchJSON("data/pois.json").catch(() => []);
    store.pois = rows.map(([lon, lat, cat, ar, fr, en]) => ({ lon, lat, cat, names: [ar, fr, en] }));
    return store.pois;
  });
}

// The line a street's numbers are measured along, [[lon, lat], ...] from its start (number 0).
export function spineOf(s) {
  if (s.spine) return s.spine;
  const lines = chainParts(s.parts);
  let line = lines[0];
  const length = l => l.reduce((sum, p, i) => sum + (i ? haversine(l[i - 1][1], l[i - 1][0], p[1], p[0]) : 0), 0);
  for (const l of lines.slice(1)) if (length(l) > length(line)) line = l;
  const far = p => haversine(p[1], p[0], s.start[1], s.start[0]);
  return (s.spine = far(line[line.length - 1]) < far(line[0]) ? line.slice().reverse() : line);
}

// The address nearest a point, among the buildings of its commune and of the communes around it:
// {address, dist} in metres, or null beyond `max`.
export async function nearestAddress(lat, lon, max = 150) {
  const pad = max / 111000, padLon = pad / Math.cos(lat * Math.PI / 180);
  const near = store.communes.filter(c => !(lon + padLon < c.bbox[0] || lon - padLon > c.bbox[2] || lat + pad < c.bbox[1] || lat - pad > c.bbox[3]));
  let best = null;
  for (const data of await Promise.all(near.map(c => loadCommune(c.id)))) {
    for (const a of data.addr) {
      if (Math.abs(a.lat - lat) > pad || Math.abs(a.lon - lon) > padLon) continue;
      const dist = haversine(lat, lon, a.lat, a.lon);
      if (dist <= max && (!best || dist < best.dist)) best = { address: a, dist };
    }
  }
  return best;
}

// The street record (with geometry and addresses) for a street id, loading its commune.
export async function streetById(sid) {
  await loadSearch();
  const row = store.streetNames.get(sid);
  if (!row) return null;
  const c = store.communes[row.c];
  const data = await loadCommune(c.id);
  return data.streetById.get(sid) ?? null;
}
