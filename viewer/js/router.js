// Turn-by-turn routing in the browser over the whole-country graph (see routing.py for the format).
// A* on travel time; one-way streets respected by car; steps use the derived street names.

import { pick, t } from "./i18n.js";
import { loadSearch, store } from "./store.js";
import { bearing, fetchJSON, haversine, norm } from "./util.js";

const TYPE_WORDS = new Set(["rue", "route", "avenue", "boulevard", "impasse", "passage", "autoroute", "autostrad",
  "street", "road", "highway", "lane", "the", "des", "del", "les", "شارع", "طريق", "جاده", "اوتوستراد"]);

let G = null;
const CELL = 0.003;            // degrees (~300 m) for the edge lookup grid
const WALK = 1.35;             // m/s

export async function loadGraph() {
  if (G) return G;
  const [meta, buf] = await Promise.all([
    fetchJSON("data/route.json"),
    fetch("data/route.bin", { cache: "no-cache" }).then(r => r.arrayBuffer()), loadSearch()]);
  const nN = meta.nodes, nE = meta.edges, nC = meta.coords;
  let off = 0;
  const take = (Type, n) => { const a = new Type(buf, off, n); off += n * Type.BYTES_PER_ELEMENT; return a; };
  const g = {
    meta, nN, nE,
    nodes: take(Float32Array, nN * 2), u: take(Int32Array, nE), v: take(Int32Array, nE), len: take(Float32Array, nE),
    label: take(Int32Array, nE), goff: take(Int32Array, nE + 1), coords: take(Float32Array, nC * 2),
    flags: take(Uint8Array, nE), cls: take(Uint8Array, nE),
  };
  g.speed = meta.classes.map(c => meta.speed_kmh[c] / 3.6);
  g.grid = new Map();
  for (let e = 0; e < nE; e++) {
    let last = -1;
    for (let i = g.goff[e]; i < g.goff[e + 1]; i++) {
      const lon = g.coords[2 * i], lat = g.coords[2 * i + 1];
      const pts = [[lon, lat]];
      if (i > g.goff[e]) {   // sample long segments so mid-segment points find the edge too
        const plon = g.coords[2 * i - 2], plat = g.coords[2 * i - 1];
        const steps = Math.ceil(Math.max(Math.abs(lon - plon), Math.abs(lat - plat)) / (CELL / 2));
        for (let k = 1; k < steps; k++) pts.push([plon + (lon - plon) * k / steps, plat + (lat - plat) * k / steps]);
      }
      for (const [x, y] of pts) {
        const key = Math.floor(x / CELL) * 100000 + Math.floor(y / CELL);
        if (key === last) continue;
        last = key;
        let list = g.grid.get(key);
        if (!list) g.grid.set(key, list = []);
        if (list[list.length - 1] !== e) list.push(e);
      }
    }
  }
  g.adj = {};
  G = g;
  return g;
}

const carOk = (g, e) => (g.flags[e] & 4) !== 0;
const footOk = (g, e) => (g.flags[e] & 8) !== 0;
const fwdOk = (g, e, mode) => (mode === "car" ? carOk(g, e) && !(g.flags[e] & 2) : footOk(g, e));
const bwdOk = (g, e, mode) => (mode === "car" ? carOk(g, e) && !(g.flags[e] & 1) : footOk(g, e));
const edgeTime = (g, e, mode) => (mode === "car" ? g.len[e] / g.speed[g.cls[e]] : g.len[e] / (g.meta.classes[g.cls[e]] === "steps" ? 0.7 : WALK));

function adjacency(g, mode) {
  if (g.adj[mode]) return g.adj[mode];
  const start = new Int32Array(g.nN + 1);
  for (let e = 0; e < g.nE; e++) {
    if (fwdOk(g, e, mode)) start[g.u[e] + 1]++;
    if (bwdOk(g, e, mode)) start[g.v[e] + 1]++;
  }
  for (let i = 0; i < g.nN; i++) start[i + 1] += start[i];
  const fill = start.slice(0, g.nN), edge = new Int32Array(start[g.nN]), rev = new Uint8Array(start[g.nN]);
  for (let e = 0; e < g.nE; e++) {
    if (fwdOk(g, e, mode)) { edge[fill[g.u[e]]] = e; rev[fill[g.u[e]]++] = 0; }
    if (bwdOk(g, e, mode)) { edge[fill[g.v[e]]] = e; rev[fill[g.v[e]]++] = 1; }
  }
  return (g.adj[mode] = { start, edge, rev });
}

function edgeCoords(g, e) {
  const out = [];
  for (let i = g.goff[e]; i < g.goff[e + 1]; i++) out.push([g.coords[2 * i], g.coords[2 * i + 1]]);
  return out;
}

// Nearest usable edge to a point; prefers the given street when it is within reach.
function snap(g, lat, lon, mode, preferLabel) {
  const ix = Math.floor(lon / CELL), iy = Math.floor(lat / CELL);
  const kx = Math.cos(lat * Math.PI / 180) * 111320, ky = 110540;
  let best = null;
  for (let r = 1; r <= 6 && !best; r++) {
    const seen = new Set();
    for (let dx = -r; dx <= r; dx++) {
      for (let dy = -r; dy <= r; dy++) {
        for (const e of g.grid.get((ix + dx) * 100000 + iy + dy) ?? []) {
          if (seen.has(e) || !(mode === "car" ? carOk(g, e) : footOk(g, e))) continue;
          seen.add(e);
          const pts = edgeCoords(g, e);
          let along = 0, cand = null;
          for (let i = 1; i < pts.length; i++) {
            const ax = pts[i - 1][0] * kx, ay = pts[i - 1][1] * ky, bx = pts[i][0] * kx, by = pts[i][1] * ky;
            const px = lon * kx, py = lat * ky, sx = bx - ax, sy = by - ay, l2 = sx * sx + sy * sy, seg = Math.sqrt(l2);
            const tt = l2 ? Math.max(0, Math.min(1, ((px - ax) * sx + (py - ay) * sy) / l2)) : 0;
            const d = Math.hypot(px - (ax + tt * sx), py - (ay + tt * sy));
            if (!cand || d < cand.dist) cand = { dist: d, along: along + tt * seg, i, tt };
            along += seg;
          }
          const score = cand.dist + (preferLabel !== undefined && g.label[e] !== preferLabel ? 30 : 0);
          if (!best || score < best.score) best = { e, score, dist: cand.dist, frac: along ? cand.along / along : 0, i: cand.i, tt: cand.tt };
        }
      }
    }
  }
  return best && best.dist < 2000 ? best : null;
}

class Heap {
  constructor() { this.k = []; this.v = []; }
  push(key, val) {
    const k = this.k, v = this.v;
    let i = k.length;
    k.push(key); v.push(val);
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (k[p] <= key) break;
      k[i] = k[p]; v[i] = v[p]; i = p;
    }
    k[i] = key; v[i] = val;
  }
  pop() {
    const k = this.k, v = this.v, topK = k[0], topV = v[0], lastK = k.pop(), lastV = v.pop();
    if (k.length) {
      let i = 0;
      for (;;) {
        let c = 2 * i + 1;
        if (c >= k.length) break;
        if (c + 1 < k.length && k[c + 1] < k[c]) c++;
        if (k[c] >= lastK) break;
        k[i] = k[c]; v[i] = v[c]; i = c;
      }
      k[i] = lastK; v[i] = lastV;
    }
    return [topK, topV];
  }
  get size() { return this.k.length; }
}

// A* from point A to point B. Returns {coords, distance, time, steps} or {error}.
export async function route(from, to, mode = "car") {
  const g = await loadGraph();
  const a = snap(g, from.lat, from.lon, mode, from.sid), b = snap(g, to.lat, to.lon, mode, to.sid);
  if (!a || !b) return { error: "route_far" };
  const { start, edge, rev } = adjacency(g, mode);
  const vmax = mode === "car" ? g.speed[0] : WALK;
  const cost = new Float64Array(g.nN).fill(Infinity), prevE = new Int32Array(g.nN).fill(-1), prevRev = new Uint8Array(g.nN);
  const done = new Uint8Array(g.nN);
  const h = n => haversine(g.nodes[2 * n + 1], g.nodes[2 * n], to.lat, to.lon) / vmax;
  const heap = new Heap();
  const seed = (n, c) => { if (c < cost[n]) { cost[n] = c; prevE[n] = -2; heap.push(c + h(n), n); } };
  const ta = edgeTime(g, a.e, mode), tb = edgeTime(g, b.e, mode);
  if (fwdOk(g, a.e, mode)) seed(g.v[a.e], (1 - a.frac) * ta);
  if (bwdOk(g, a.e, mode)) seed(g.u[a.e], a.frac * ta);
  const finish = new Map();   // node -> [extra time to reach B, direction along b.e]
  if (fwdOk(g, b.e, mode)) finish.set(g.u[b.e], [b.frac * tb, 0]);
  if (bwdOk(g, b.e, mode)) finish.set(g.v[b.e], [(1 - b.frac) * tb, 1]);

  let best = Infinity, bestNode = -1, direct = null;
  if (a.e === b.e) {
    if (fwdOk(g, a.e, mode) && a.frac <= b.frac) direct = { time: (b.frac - a.frac) * ta, rev: 0 };
    else if (bwdOk(g, a.e, mode) && b.frac <= a.frac) direct = { time: (a.frac - b.frac) * ta, rev: 1 };
    if (direct) best = direct.time;
  }
  while (heap.size) {
    const [key, n] = heap.pop();
    if (key >= best) break;
    if (done[n]) continue;
    done[n] = 1;
    const fin = finish.get(n);
    if (fin && cost[n] + fin[0] < best) { best = cost[n] + fin[0]; bestNode = n; direct = null; }
    for (let k = start[n]; k < start[n + 1]; k++) {
      const e = edge[k], r = rev[k], m = r ? g.u[e] : g.v[e];
      const c = cost[n] + edgeTime(g, e, mode);
      if (c < cost[m]) {
        cost[m] = c; prevE[m] = e; prevRev[m] = r;
        heap.push(c + h(m), m);
      }
    }
  }
  if (best === Infinity) return { error: "route_none" };

  // Pieces as [edge, reversed, fromFrac, toFrac] along the edge's own direction.
  const pieces = [];
  if (direct) {
    pieces.push([a.e, direct.rev, a.frac, b.frac]);
  } else {
    const fin = finish.get(bestNode);
    pieces.push([b.e, fin[1], fin[1] ? 1 : 0, b.frac]);
    let n = bestNode;
    while (prevE[n] >= 0) {
      const e = prevE[n], r = prevRev[n];
      pieces.push([e, r, r ? 1 : 0, r ? 0 : 1]);
      n = r ? g.v[e] : g.u[e];
    }
    pieces.push(n === g.v[a.e] ? [a.e, 0, a.frac, 1] : [a.e, 1, a.frac, 0]);
    pieces.reverse();
  }
  return describeRoute(g, pieces, mode, from, to);
}

function cut(pts, f0, f1) {
  // Sub-polyline between fractions f0 and f1 of the length (f0 > f1 means reversed).
  const cum = [0];
  for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + haversine(pts[i - 1][1], pts[i - 1][0], pts[i][1], pts[i][0]));
  const L = cum[cum.length - 1] || 1;
  const at = d => {
    let i = 1;
    while (i < cum.length - 1 && cum[i] < d) i++;
    const s = cum[i] - cum[i - 1] || 1, tt = Math.max(0, Math.min(1, (d - cum[i - 1]) / s));
    return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * tt, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * tt];
  };
  const lo = Math.min(f0, f1) * L, hi = Math.max(f0, f1) * L;
  const out = [at(lo), ...pts.filter((_, i) => cum[i] > lo && cum[i] < hi), at(hi)];
  return f0 > f1 ? out.reverse() : out;
}

function streetName(g, e) {
  const lab = g.label[e];
  if (lab >= 0) {
    const row = store.streetNames?.get(lab);
    if (row) return pick(row.names);
  }
  if (lab <= -2) return pick(g.meta.names[-(lab + 2)]);
  const c = g.meta.classes[g.cls[e]];
  if (g.flags[e] & 16) return t("cls_roundabout");
  if (c === "motorway") return t("cls_motorway");
  if (c.endsWith("_link")) return t("cls_link");
  if (c === "track") return t("cls_track");
  if (c === "steps") return t("cls_steps");
  if (c === "footway" || c === "pedestrian") return t("cls_footway");
  return t("cls_road");
}

const COMPASS = ["dir_n", "dir_ne", "dir_e", "dir_se", "dir_s", "dir_sw", "dir_w", "dir_nw"];

function headingAt(coords, fromEnd, metres = 25) {
  // Bearing over the first (or last) `metres` of a polyline.
  const pts = fromEnd ? [...coords].reverse() : coords;
  let d = 0, j = 1;
  while (j < pts.length - 1 && d < metres) { d += haversine(pts[j - 1][1], pts[j - 1][0], pts[j][1], pts[j][0]); j++; }
  const [p, q] = fromEnd ? [pts[j], pts[0]] : [pts[0], pts[j]];
  return bearing(p[1], p[0], q[1], q[0]);
}

function describeRoute(g, pieces, mode, from, to) {
  const legs = [];
  for (const [e, , f0, f1] of pieces) {
    const coords = cut(edgeCoords(g, e), f0, f1);
    const length = g.len[e] * Math.abs(f1 - f0);
    if (length < 0.5) continue;
    // Consecutive pieces with the same name are one instruction, even across commune lines.
    const name = streetName(g, e);
    const round = !!(g.flags[e] & 16);
    const key = round ? "round" : g.label[e] !== -1 ? `n:${name}` : `c${g.cls[e]}`;
    const last = legs[legs.length - 1];
    const time = edgeTime(g, e, mode) * Math.abs(f1 - f0);
    if (last && last.key === key) {
      last.coords.push(...coords.slice(1));
      last.length += length;
      last.time += time;
    } else {
      const lab = g.label[e];
      const unnamed = !(lab >= 0 && store.streetNames?.has(lab)) && lab > -2;
      // generic: a plain road with no name at all (not a ramp, a track or a path, which say what they are)
      legs.push({ key, e, coords, length, time, round, name, unnamed, generic: unnamed && !round && name === t("cls_road") });
    }
  }
  // Fold tiny unnamed connectors into the next leg so they don't become their own instruction,
  // then join neighbours that now carry the same name.
  const join = (i, j) => {
    legs[j].coords = j > i ? [...legs[i].coords, ...legs[j].coords.slice(1)] : [...legs[j].coords, ...legs[i].coords.slice(1)];
    legs[j].length += legs[i].length;
    legs[j].time += legs[i].time;
    legs.splice(i, 1);
  };
  for (let i = legs.length - 2; i >= 0; i--) {
    if (legs[i].length < 40 && (legs[i].key.startsWith("c") || legs[i].unnamed)) join(i, i + 1);
  }
  // One road tagged differently along its length ("Avenue Camile Chamoun", "Camile Chamoun Avenue",
  // "Autoroute Maritime - Viaduc Cola") is one instruction: names whose words contain each other.
  const words = name => new Set(norm(name).split(" ").filter(w => w.length > 2 && !TYPE_WORDS.has(w)));
  // A side street named after the street it leaves ("Cedar Lane 561" off "Cedar Street") is another
  // road: the numbers in two names of one road are the same.
  const numbers = name => norm(name).split(" ").filter(w => /^\d+$/.test(w)).join(" ");
  const sameRoad = (x, y) => {
    const a = words(x), b = words(y);
    if (!a.size || !b.size || numbers(x) !== numbers(y)) return false;
    const [small, big] = a.size <= b.size ? [a, b] : [b, a];
    return [...small].every(w => big.has(w));
  };
  for (let i = legs.length - 1; i > 0; i--) {
    const prev = legs[i - 1], cur = legs[i];
    if (cur.round || prev.round) continue;
    if (cur.key === prev.key || sameRoad(cur.name, prev.name)) {
      if (cur.length > prev.length) prev.name = cur.name;   // keep the name of the longer stretch
      join(i, i - 1);
    }
  }
  const steps = [];
  let total = 0, time = 0;
  legs.forEach((leg, i) => {
    total += leg.length;
    time += leg.time;
    if (leg.round) return;   // announced with the exit that follows
    const [lon, lat] = leg.coords[0];
    // A road with no name is told by the street it leads to ("take the exit toward Hawthorn
    // Lane"), or by the destination when no named street follows.
    const ahead = leg.generic ? legs.slice(i + 1).find(l => !l.unnamed)?.name ?? to.label : null;
    const say = (key, vars = {}) => (ahead ? t(`${key}_toward`, { ...vars, street: ahead }) : t(key, { ...vars, street: leg.name }));
    let text, turn;   // turn: the manoeuvre, for the step's icon
    if (i === 0) {
      turn = "depart";
      text = say("depart", { dir: t(COMPASS[Math.round(headingAt(leg.coords, false) / 45) % 8]) });
    } else if (legs[i - 1].round) {
      turn = "roundabout";
      text = say("roundabout");
    } else {
      const delta = ((headingAt(leg.coords, false) - headingAt(legs[i - 1].coords, true) + 540) % 360) - 180;
      const side = delta > 0 ? "right" : "left", abs = Math.abs(delta);
      turn = abs < 20 ? "continue" : abs < 55 ? `slight_${side}` : abs < 135 ? `turn_${side}` : abs < 165 ? `sharp_${side}` : "uturn";
      text = say(turn);
    }
    steps.push({ text, turn, dist: leg.length, lat, lon });
  });
  const coords = legs.flatMap((l, i) => (i ? l.coords.slice(1) : l.coords));
  // Which side of the street the destination is on, relative to the direction of travel.
  const end = coords[coords.length - 1], prev = coords[Math.max(0, coords.length - 2)];
  const kx = Math.cos(end[1] * Math.PI / 180);
  const cross = (end[0] - prev[0]) * kx * (to.lat - end[1]) - (end[1] - prev[1]) * (to.lon - end[0]) * kx;
  const place = to.label ?? t("my_point");
  steps.push({
    text: haversine(end[1], end[0], to.lat, to.lon) > 3 ? t("arrive", { place, side: t(cross > 0 ? "on_left" : "on_right") }) : t("arrive_plain", { place }),
    turn: "arrive", dist: 0, lat: to.lat, lon: to.lon, arrive: true,
  });
  return { coords, distance: total, time, steps };
}
