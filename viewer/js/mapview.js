// The Leaflet map: base maps, boundaries, streets, buildings, labels, selection and route layers.

import { lang, pick } from "./i18n.js";
import { LabelOverlay } from "./labels.js";
import { communeAt, loadBuildings, loadCommune, store } from "./store.js";
import { chainParts, fetchJSON } from "./util.js";

export const selection = { street: null, address: null, commune: null };
// Pixels of the map hidden by the interface: the card beside it on a desktop (`start`: on the left,
// or the right in Arabic), the search bar above and the sheet below on a phone.
export const insets = { top: 0, bottom: 0, start: 0 };
const ACCENT = "#1F4AA8";
export const view = {
  colorBySource: false,
  show: { buildings: true, numbers: true, boundaries: true, labels: true },
  base: "plain",
};
const handlers = {};
export const on = (name, fn) => { handlers[name] = fn; };
const emit = (name, ...args) => handlers[name]?.(...args);

export const map = L.map("map", {
  zoomControl: false, minZoom: 8, maxZoom: 20, zoomSnap: 0.5, wheelPxPerZoomLevel: 90,
  maxBounds: [[32.6, 34.6], [35.1, 37.2]], maxBoundsViscosity: 0.8, attributionControl: true,
}).setView([33.88, 35.6], 9);
L.control.scale({ imperial: false, position: "bottomright" }).addTo(map);

for (const [name, z] of [["bgPane", 350], ["fgPane", 400], ["selPane", 450], ["labelPane", 620]]) {
  map.createPane(name).style.zIndex = z;
}
map.getPane("labelPane").style.pointerEvents = "none";
const bg = L.canvas({ pane: "bgPane", padding: 0.3 });
const fg = L.canvas({ pane: "fgPane", padding: 0.3, tolerance: 5 });
const sel = L.canvas({ pane: "selPane", padding: 0.3 });

const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/";
const BASES = {
  // Drawn by the viewer from the map's own data (land, main roads, streets, buildings): no tiles
  // and no outside service, so a published copy depends on nobody's terms.
  plain: null,
  osm: L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxZoom: 20, maxNativeZoom: 19, attribution: "Tiles &copy; OpenStreetMap", className: "osm-tiles" }),
  // Zoom 15+ tiles of this basemap carry Esri's own street labels, which would contradict ours;
  // zoom-14 tiles have none, so they are stretched beyond that and faded under our streets.
  light: L.tileLayer(ESRI + "Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 20, maxNativeZoom: 14, attribution: "Basemap &copy; Esri", className: "light-tiles" }),
  terrain: L.tileLayer(ESRI + "Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 20, maxNativeZoom: 16, attribution: "Hillshade &copy; Esri", className: "terrain-tiles" }),
  sat: L.tileLayer(ESRI + "World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 20, maxNativeZoom: 19, attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics" }),
};
document.body.dataset.base = view.base;
map.attributionControl.setPrefix(false);
map.attributionControl.addAttribution('Data &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors (ODbL)');
map.attributionControl.addAttribution('Boundaries &copy; <a href="https://data.humdata.org/dataset/cod-ab-lbn" target="_blank" rel="noopener">OCHA</a> (CC BY-IGO)');
map.attributionControl.addAttribution('Driveways &copy; <a href="https://github.com/microsoft/RoadDetections" target="_blank" rel="noopener">Microsoft</a> (ODbL)');

export function setBase(name) {
  Object.values(BASES).forEach(l => l && map.removeLayer(l));
  BASES[name]?.addTo(map);
  view.base = name;
  document.body.dataset.base = name;
  updateBoundaries();
  refresh();
  restyleAll();
}

// ---------- styles ----------
const CLASS_STYLE = {  // [fill, casing, width at z16]
  motorway: ["#ea8a6c", "#b65a3e", 8], trunk: ["#ef9a55", "#b9692c", 7], primary: ["#f6b862", "#c4873a", 6.5], secondary: ["#f8d775", "#c3a647", 6],
  tertiary: ["#fff3b0", "#bdb07a", 5.5], unclassified: ["#ffffff", "#b4aea6", 4.5], residential: ["#ffffff", "#b4aea6", 4.5],
  living_street: ["#ffffff", "#b4aea6", 3.5], road: ["#ffffff", "#b4aea6", 3.5], service: ["#ffffff", "#c2bcb5", 3],
  pedestrian: ["#f3eef5", "#c4b6cc", 3],
};
export const SRC_COLOR = ["#3b4350", "#8a3ffc", "#0f7f8c", "#d96c00", "#2e9d4f", "#3f7fd6", "#c2185b"];
const BUILDING_STYLE = [  // [fill, stroke] by category: regular, worship, minor, public
  ["#d9cfc5", "#b7aa9d"], ["#d8c8f0", "#9c84cc"], ["#e9e7e4", "#cfcac4"], ["#f2d8bd", "#cf9f6c"],
];

const widthAt = (base, z) => Math.max(1, base * Math.pow(2, (z - 16) * 0.55));

function streetStyle(s, z, hover = false) {
  const [fill, , w] = CLASS_STYLE[s.highway] ?? CLASS_STYLE.residential;
  const color = hover ? ACCENT : view.colorBySource ? SRC_COLOR[s.src] : fill;
  return { color, weight: widthAt(w, z), opacity: view.base === "sat" && !view.colorBySource ? 0.85 : 1,
    lineCap: "round", lineJoin: "round" };
}

function casingStyle(s, z) {
  const [, casing, w] = CLASS_STYLE[s.highway] ?? CLASS_STYLE.residential;
  return { color: view.colorBySource ? "#ffffff" : casing, weight: widthAt(w, z) + 2, opacity: 1,
    lineCap: "round", lineJoin: "round" };
}

// The commune's other roads -- motorways, ramps, roundabouts, stretches with no name, tracks and
// paths -- drawn on the plain base map, where no tiles show them: [casing style or null, line style].
const PATH_STYLE = { track: { color: "#b3a182", weight: 1.6, dashArray: "7 5" }, footway: { color: "#c0988a", weight: 1.4, dashArray: "2 5" },
  steps: { color: "#c0988a", weight: 2.4, dashArray: "1 4" } };
const WAY_RANK = ["track", "footway", "steps", "service", "pedestrian", "living_street", "road", "residential", "unclassified", "tertiary_link",
  "tertiary", "secondary_link", "secondary", "primary_link", "primary", "trunk_link", "trunk", "motorway_link", "motorway"];
function wayStyle(highway, z) {
  if (PATH_STYLE[highway]) return [null, { ...PATH_STYLE[highway], opacity: z >= 15.5 ? 1 : 0 }];
  const base = highway.replace("_link", "");
  const [fill, casing, w] = CLASS_STYLE[base] ?? CLASS_STYLE.residential;
  const weight = widthAt(w * (base === highway ? 1 : 0.65), z);
  return [{ color: casing, weight: weight + 2 }, { color: fill, weight }];
}

function buildingStyle(b) {
  const [fill, stroke] = BUILDING_STYLE[b.cat] ?? BUILDING_STYLE[0];
  const sat = view.base === "sat";
  return { color: sat ? "#ffffff" : stroke, weight: sat ? 0.8 : 0.7, fillColor: b.addr >= 0 || b.cat ? fill : "#e6e1dc",
    fillOpacity: sat ? 0.18 : 0.95, opacity: sat ? 0.7 : 1 };
}

// ---------- boundaries ----------
const govLayer = L.layerGroup(), distLayer = L.layerGroup(), communeLayer = L.layerGroup();
const contestedLayer = L.layerGroup();
// The plain base map: the country's land, and its main roads where no commune's streets are loaded.
const landLayer = L.layerGroup(), roadLayers = [0, 1, 2, 3].map(() => L.layerGroup());
// They are simplified to 15 m: an overview, replaced from ROAD_MAX_ZOOM by each commune's own roads at
// full detail (drawCommuneStreets), which load from zoom 14.
const ROAD_CLASS = ["trunk", "primary", "secondary", "tertiary"], ROAD_MIN_ZOOM = [8, 9, 10.5, 12], ROAD_MAX_ZOOM = 15;
const roadWeight = (cls, z) => Math.max([1.8, 1.4, 1.1, 1][cls], widthAt(CLASS_STYLE[ROAD_CLASS[cls]][2], z));

async function drawRoads() {
  const rows = await fetchJSON("data/roads.json").catch(() => []);
  const z = map.getZoom();
  for (const [cls, line] of rows) {
    const [fill, casing] = CLASS_STYLE[ROAD_CLASS[cls]], latlngs = line.map(([x, y]) => [y, x]);
    const style = { renderer: bg, interactive: false, lineCap: "round", lineJoin: "round" };
    roadLayers[cls].addLayer(L.polyline(latlngs, { ...style, color: casing, weight: roadWeight(cls, z) + 1.5, casing: true }));
    roadLayers[cls].addLayer(L.polyline(latlngs, { ...style, color: fill, weight: roadWeight(cls, z) }));
  }
  updateBoundaries();
}

export function drawBoundaries() {
  for (const g of store.governorates) {
    landLayer.addLayer(L.polygon(g.polys, { renderer: bg, interactive: false, color: "#f8f6f1", weight: 1, fillColor: "#f8f6f1", fillOpacity: 1 }));
  }
  drawRoads();
  for (const g of store.governorates) {
    govLayer.addLayer(L.polygon(g.polys, { renderer: bg, interactive: false, fill: false, color: "#6c4f8c", weight: 2.6, opacity: 0.75 }));
  }
  for (const d of store.districts) {
    distLayer.addLayer(L.polygon(d.polys, { renderer: bg, interactive: false, fill: false, color: "#8f78a8", weight: 1.6, opacity: 0.8, dashArray: "8 5" }));
  }
  // Areas OCHA lists as contested between neighbouring cadasters.
  for (const polys of store.contested) {
    contestedLayer.addLayer(L.polygon(polys, { renderer: bg, interactive: false, color: "#d9822b", weight: 1.4,
      opacity: 0.9, dashArray: "2 4", fillColor: "#f2a541", fillOpacity: 0.16 }));
  }
  for (const c of store.communes) {
    if (c.est) {
      communeLayer.addLayer(L.polygon(c.polys, { renderer: bg, interactive: false, fill: false, color: "#8a8f99", weight: 1, opacity: 0.9, dashArray: "3 4" }));
    } else {
      communeLayer.addLayer(L.polygon(c.osmPolys ?? c.polys, { renderer: bg, interactive: false, fill: false, color: "#7b8494", weight: 1.2, opacity: 0.95 }));
    }
  }
  updateBoundaries();
}

function updateBoundaries() {
  const z = map.getZoom(), show = view.show.boundaries;
  const plain = view.base === "plain";
  const want = [[landLayer, plain], [govLayer, show && z < 13], [distLayer, show && z >= 9 && z < 14], [communeLayer, show && z >= 10.5],
    [contestedLayer, show && z >= 10.5], ...roadLayers.map((layer, cls) => [layer, plain && z >= ROAD_MIN_ZOOM[cls] && z < ROAD_MAX_ZOOM])];
  for (const [layer, visible] of want) {
    if (visible && !map.hasLayer(layer)) {
      layer.addTo(map);
      if (layer === landLayer) layer.eachLayer(l => l.bringToBack());   // under the boundaries drawn before it
    }
    if (!visible && map.hasLayer(layer)) map.removeLayer(layer);
  }
}

// ---------- streets and buildings per commune ----------
const drawn = new Map();      // commune id -> {streets: [{s, casing, line}], group, casingGroup}
const drawnBuildings = new Map();
let hoverTip = null;

function drawCommuneStreets(data) {
  if (drawn.has(data.id)) return;
  const z = map.getZoom();
  const group = L.layerGroup(), casingGroup = L.layerGroup(), items = [];
  for (const s of data.streets) {
    const latlngs = s.parts.map(p => p.map(([x, y]) => [y, x]));
    const casing = L.polyline(latlngs, { renderer: bg, interactive: false, ...casingStyle(s, z) });
    const line = L.polyline(latlngs, { renderer: fg, bubblingMouseEvents: false, ...streetStyle(s, z) });
    line.on("click", e => emit("street", s, e.latlng));
    line.on("mouseover", e => {
      line.setStyle(streetStyle(s, map.getZoom(), true));
      hoverTip = L.tooltip({ sticky: true, direction: "top", offset: [0, -8], className: "street-tip" })
        .setLatLng(e.latlng).setContent(escapeHTML(pick(s.names))).addTo(map);
      map.getContainer().style.cursor = "pointer";
    });
    line.on("mousemove", e => hoverTip?.setLatLng(e.latlng));
    line.on("mouseout", () => {
      line.setStyle(streetStyle(s, map.getZoom()));
      hoverTip?.remove();
      hoverTip = null;
      map.getContainer().style.cursor = "";
    });
    casingGroup.addLayer(casing);
    group.addLayer(line);
    items.push({ s, casing, line });
  }
  // Paths first and motorways last, every casing under every line, so that roads join cleanly.
  const otherGroup = L.layerGroup(), flat = { renderer: bg, interactive: false, lineCap: "round", lineJoin: "round" };
  const others = [...data.ways].sort((a, b) => WAY_RANK.indexOf(a[0]) - WAY_RANK.indexOf(b[0])).map(([highway, lines]) => {
    const latlngs = lines.map(p => p.map(([x, y]) => [y, x])), [casing, line] = wayStyle(highway, z);
    return { highway, casing: casing && L.polyline(latlngs, { ...flat, ...casing }), line: L.polyline(latlngs, { ...flat, ...line }) };
  });
  for (const o of others) if (o.casing) otherGroup.addLayer(o.casing);
  for (const o of others) otherGroup.addLayer(o.line);
  drawn.set(data.id, { items, group, casingGroup, otherGroup, others });
}

function drawCommuneBuildings(id, list, data) {
  if (drawnBuildings.has(id)) return;
  const group = L.layerGroup();
  for (const b of list) {
    const poly = L.polygon(b.ring, { renderer: fg, bubblingMouseEvents: false, ...buildingStyle(b) });
    poly.on("click", e => emit("building", b, data, e.latlng));
    poly.on("mouseover", () => poly.setStyle({ fillColor: "#c9b7a6" }));
    poly.on("mouseout", () => poly.setStyle(buildingStyle(b)));
    b.layer = poly;
    group.addLayer(poly);
  }
  drawnBuildings.set(id, group);
}

function restyleAll() {
  const z = map.getZoom();
  for (const { items } of drawn.values()) {
    for (const { s, casing, line } of items) {
      casing.setStyle(casingStyle(s, z));
      line.setStyle(streetStyle(s, z));
    }
  }
  for (const [id] of drawnBuildings) {
    for (const b of store.buildings.get(id) ?? []) b.layer?.setStyle(buildingStyle(b));
  }
  labels.redraw();
}

export function setColorBySource(on) {
  view.colorBySource = on;
  restyleAll();
}

export function setShow(key, on) {
  view.show[key] = on;
  updateBoundaries();
  refresh();
  labels.redraw();
}

const inView = (bbox, b) => !(bbox[2] < b.getWest() || bbox[0] > b.getEast() || bbox[3] < b.getSouth() || bbox[1] > b.getNorth());

let refreshToken = 0;
export async function refresh() {
  const token = ++refreshToken;
  const z = map.getZoom(), b = map.getBounds().pad(0.15), center = map.getCenter();
  updateBoundaries();
  const near = store.communes.filter(c => inView(c.bbox, b)).sort((a, c) =>
    Math.hypot(a.label[0] - center.lng, a.label[1] - center.lat) - Math.hypot(c.label[0] - center.lng, c.label[1] - center.lat));
  const streetIds = new Set(z >= 14 ? near.slice(0, 45).map(c => c.id) : []);
  const buildingIds = new Set(z >= 15 && view.show.buildings ? near.slice(0, 30).map(c => c.id) : []);

  for (const [id, d] of drawn) {
    if (!streetIds.has(id)) { map.removeLayer(d.group); map.removeLayer(d.casingGroup); }
    if (!streetIds.has(id) || view.base !== "plain") map.removeLayer(d.otherGroup);
  }
  for (const [id, g] of drawnBuildings) {
    if (!buildingIds.has(id)) map.removeLayer(g);
  }
  if (drawn.size > 120) {  // free memory far from the view
    for (const [id] of drawn) if (!streetIds.has(id)) drawn.delete(id);
  }

  const loads = [...streetIds].map(async id => {
    const data = await loadCommune(id);
    if (token !== refreshToken) return;
    drawCommuneStreets(data);
    const d = drawn.get(id);
    if (!map.hasLayer(d.casingGroup)) d.casingGroup.addTo(map);
    if (view.base === "plain" && !map.hasLayer(d.otherGroup)) d.otherGroup.addTo(map);
    if (!map.hasLayer(d.group)) d.group.addTo(map);
  });
  // Buildings load on their own: a commune can have buildings but no named street.
  loads.push(...[...buildingIds].map(async id => {
    const [data, list] = await Promise.all([loadCommune(id), loadBuildings(id)]);
    if (token !== refreshToken) return;
    drawCommuneBuildings(id, list, data);
    const g = drawnBuildings.get(id);
    if (!map.hasLayer(g)) {
      g.addTo(map);
      g.eachLayer(l => l.bringToBack());
    }
  }));
  await Promise.all(loads);
  if (token === refreshToken) labels.redraw();
}

map.on("zoomend", () => {
  const z = map.getZoom();
  BASES.light.setOpacity(z >= 16 ? 0.55 : z >= 15 ? 0.75 : 1);
  roadLayers.forEach((layer, cls) => layer.eachLayer(l => l.setStyle({ weight: roadWeight(cls, z) + (l.options.casing ? 1.5 : 0) })));
  for (const { items, others } of drawn.values()) {
    for (const { s, casing, line } of items) {
      casing.setStyle({ weight: casingStyle(s, z).weight });
      line.setStyle({ weight: streetStyle(s, z).weight });
    }
    for (const { highway, casing, line } of others) {
      const [c, l] = wayStyle(highway, z);
      casing?.setStyle(c);
      line.setStyle(l);
    }
  }
  updateBoundaries();
});
map.on("moveend", () => refresh());

// ---------- labels ----------
const FONTS = {
  gov: "700 15px system-ui, sans-serif", dist: "600 13px system-ui, sans-serif",
  city: "700 15px system-ui, sans-serif", town: "700 13px system-ui, sans-serif", village: "600 12px system-ui, sans-serif",
  place: "500 11px system-ui, sans-serif", street: "600 11.5px system-ui, sans-serif", num: "700 10px system-ui, sans-serif",
};
const KIND_MIN_ZOOM = [8.5, 10.5, 11.5, 12.5];   // city, town, village, quarter
const PLACE_MIN_ZOOM = [8, 10.5, 12, 13, 14.5, 15.5];   // city, town, village, suburb, hamlet, locality
const ANCHOR_Z = 18;

const LABEL_SPACING_PX = 450;

// Label anchors for a street at a given zoom: one every ~LABEL_SPACING_PX on screen along each
// continuous line, with the angle of the street around that point (kept upright).
function streetAnchors(s, z) {
  const bucket = Math.round(z);
  s.anchors ??= {};
  if (s.anchors[bucket]) return s.anchors[bucket];
  s.lines18 ??= chainParts(s.parts).map(line => {
    const pts = line.map(([x, y]) => map.project([y, x], ANCHOR_Z));
    const cum = [0];
    for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + pts[i].distanceTo(pts[i - 1]));
    return { pts, cum, L: cum[cum.length - 1] };
  });
  const spacing = LABEL_SPACING_PX * Math.pow(2, ANCHOR_Z - bucket);
  const anchors = [];
  for (const { pts, cum, L: L18 } of s.lines18) {
    if (L18 < 60) continue;
    const n = Math.max(1, Math.round(L18 / spacing));
    for (let k = 0; k < n; k++) {
      const target = (k + 0.5) * L18 / n;
      const p = pointAt(pts, cum, target);
      const win = 30 * Math.pow(2, ANCHOR_Z - bucket);  // ~30 screen px each way
      const back = pointAt(pts, cum, Math.max(0, target - win)), fwd = pointAt(pts, cum, Math.min(L18, target + win));
      let ang = Math.atan2(fwd.y - back.y, fwd.x - back.x) * 180 / Math.PI;
      if (ang > 90) ang -= 180;
      if (ang < -90) ang += 180;
      const ll = map.unproject(p, ANCHOR_Z);
      anchors.push({ lat: ll.lat, lng: ll.lng, angle: ang, len18: L18 / n });
    }
  }
  s.anchors[bucket] = anchors;
  return anchors;
}

function pointAt(pts, cum, d) {
  let i = 1;
  while (i < cum.length - 1 && cum[i] < d) i++;
  const a = pts[i - 1], b = pts[i], seg = cum[i] - cum[i - 1] || 1, t = Math.max(0, Math.min(1, (d - cum[i - 1]) / seg));
  return L.point(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t);
}

const STREET_PRIO = { trunk: 60, primary: 55, secondary: 50, tertiary: 45, unclassified: 40, residential: 38 };

function labelCandidates(z, b) {
  const out = [];
  const contains = (lat, lng) => lat >= b.getSouth() && lat <= b.getNorth() && lng >= b.getWest() && lng <= b.getEast();
  if (view.show.labels) {
    if (z < 10) {
      for (const g of store.governorates) {
        if (z < 9.5 && contains(g.label[1], g.label[0])) out.push({ lat: g.label[1], lng: g.label[0], text: pick([g.ar, g.fr, g.en]), cls: "gov", font: FONTS.gov, prio: 900 });
      }
    }
    if (z >= 9.5 && z < 11.5) {
      for (const d of store.districts) {
        if (contains(d.label[1], d.label[0])) out.push({ lat: d.label[1], lng: d.label[0], text: pick([d.ar, d.fr, d.en]), cls: "dist", font: FONTS.dist, prio: 800 });
      }
    }
    for (const c of store.communes) {
      if (z < KIND_MIN_ZOOM[c.kind] || z >= 17.5 || !contains(c.label[1], c.label[0])) continue;
      const cls = ["city", "town", "village", "village"][c.kind];
      out.push({ lat: c.label[1], lng: c.label[0], text: pick([c.ar, c.fr, c.en]), cls: `commune ${cls}${c.est ? " est" : ""}`,
        font: FONTS[cls], prio: 700 - c.kind * 40 + Math.min(30, Math.log10((c.pop ?? c.addr) + 1) * 8), pad: 4,
        onClick: () => emit("commune", c) });
    }
    for (const p of store.places) {
      // Settlements without a commune of their own (Beirut, Jounieh, villages inside a larger commune).
      if (z < PLACE_MIN_ZOOM[p.type] || !contains(p.lat, p.lon)) continue;
      const big = p.type <= 2;
      const cls = big ? ["city", "town", "village"][p.type] : "place";
      out.push({ lat: p.lat, lng: p.lon, text: pick(p.names), cls: big ? `commune ${cls}` : "place",
        font: big ? FONTS[cls] : FONTS.place, prio: big ? [860, 700, 660][p.type] : 350 - p.type * 10, pad: 4 });
    }
  }
  if (z >= 15) {
    for (const [id, d] of drawn) {
      if (!map.hasLayer(d.group)) continue;
      for (const { s } of d.items) {
        const base = STREET_PRIO[s.highway] ?? 30;
        if (z < 16 && base < 45) continue;
        const text = pick(s.names);
        for (const a of streetAnchors(s, z)) {
          if (!contains(a.lat, a.lng)) continue;
          const lenNow = a.len18 * Math.pow(2, z - ANCHOR_Z);
          const need = text.length * 6.5 + 24;
          if (lenNow < need) continue;
          out.push({ lat: a.lat, lng: a.lng, angle: a.angle, text, cls: `street${view.base === "sat" ? " on-sat" : ""}`, font: FONTS.street,
            prio: 200 + base + Math.min(20, s.len / 100), key: s.sid, minSep: 320, pad: 2,
            onClick: () => emit("street", s) });
        }
      }
    }
  }
  if (z >= 17 && view.show.numbers) {
    for (const [id, d] of drawn) {
      if (!map.hasLayer(d.group)) continue;
      const data = store.loaded.get(id);
      for (const a of data?.addr ?? []) {
        if (!contains(a.lat, a.lon)) continue;
        out.push({ lat: a.lat, lng: a.lon, text: String(a.num), cls: `num ${a.side ? "even" : "odd"}`, font: FONTS.num,
          prio: 100 + (a === selection.address ? 500 : 0), pad: 2, onClick: () => emit("address", a) });
      }
    }
  }
  if (selection.street && z >= 15) {
    const [x, y] = selection.street.start;
    out.push({ lat: y, lng: x, text: "0", cls: "start", font: FONTS.num, prio: 1000, pad: 4 });
  }
  return out;
}

export const labels = new LabelOverlay(labelCandidates).addTo(map);

const sidePad = () => (document.documentElement.dir === "rtl" ? [0, insets.start] : [insets.start, 0]);

function fitTo(bounds, maxZoom = 18) {
  const [left, right] = sidePad();
  map.fitBounds(bounds, { maxZoom, paddingTopLeft: [40 + left, 40 + insets.top], paddingBottomRight: [40 + right, 40 + insets.bottom],
    animate: false });
}

function centerOn(latlng, zoom) {
  map.setView(latlng, zoom, { animate: false });
  const [left, right] = sidePad();
  const dx = (right - left) / 2, dy = (insets.bottom - insets.top) / 2;
  if (dx || dy) map.panBy([dx, dy], { animate: false });
}

// ---------- selection ----------
const selLayer = L.layerGroup().addTo(map);

export function clearSelection() {
  selLayer.clearLayers();
  selection.street = selection.address = selection.commune = null;
  labels.redraw();
}

export function highlightStreet(s, fit = false) {
  clearSelection();
  selection.street = s;
  const latlngs = s.parts.map(p => p.map(([x, y]) => [y, x]));
  selLayer.addLayer(L.polyline(latlngs, { renderer: sel, interactive: false, color: ACCENT, weight: 12, opacity: 0.28, lineCap: "round" }));
  selLayer.addLayer(L.polyline(latlngs, { renderer: sel, interactive: false, color: ACCENT, weight: 3, opacity: 0.9, lineCap: "round" }));
  if (fit) fitTo(L.latLngBounds(latlngs.flat()));
  labels.redraw();
}

// The number on a sign above its place: solid for a building, dashed for a number no building has.
const plaque = (lat, lon, text, approx = false) => L.marker([lat, lon], { interactive: false, keyboard: false,
  icon: L.divIcon({ className: "", iconSize: [0, 0], html: `<div class="map-plaque${approx ? " approx" : ""}">${escapeHTML(text)}</div>` }) });

// label: the number the building is shown under (its own, or an alias's).
export function highlightAddress(a, ring, fly = false, label = a.num) {
  clearSelection();
  selection.address = a;
  if (ring) selLayer.addLayer(L.polygon(ring, { renderer: sel, interactive: false, color: ACCENT, weight: 3, fillColor: ACCENT, fillOpacity: 0.25 }));
  if (a.access) {   // the driveway it is reached by, from the street
    selLayer.addLayer(L.polyline(a.access[1].map(([x, y]) => [y, x]), { renderer: sel, interactive: false,
      color: ACCENT, weight: 3, opacity: 0.9, dashArray: "6 5", lineCap: "round" }));
  }
  selLayer.addLayer(plaque(a.lat, a.lon, label));
  if (fly) centerOn([a.lat, a.lon], Math.max(map.getZoom(), 18));
  labels.redraw();
}

// A point that is no building: the place of a number on its street (label: that number), or a named place.
export function highlightSpot(lat, lon, fly = false, label = null) {
  clearSelection();
  selLayer.addLayer(L.circleMarker([lat, lon], { renderer: sel, interactive: false, radius: 15, color: ACCENT, weight: 2.5, dashArray: "5 5",
    fillColor: ACCENT, fillOpacity: 0.12 }));
  selLayer.addLayer(L.circleMarker([lat, lon], { renderer: sel, interactive: false, radius: 6, color: "#fff", weight: 2.5, fillColor: ACCENT, fillOpacity: 1 }));
  if (label !== null) selLayer.addLayer(plaque(lat, lon, label, true));
  if (fly) centerOn([lat, lon], Math.max(map.getZoom(), 18));
  labels.redraw();
}

export function highlightCommune(c, fit = false) {
  clearSelection();
  selection.commune = c;
  selLayer.addLayer(L.polygon(c.polys, { renderer: sel, interactive: false, color: ACCENT, weight: 2.5, fillColor: ACCENT, fillOpacity: 0.06 }));
  if (fit) {
    const [x0, y0, x1, y1] = c.bbox;
    fitTo([[y0, x0], [y1, x1]], 16);
  }
}

// ---------- route ----------
const routeLayer = L.layerGroup().addTo(map);
const pinIcon = label => L.divIcon({ className: "", html: `<div class="pin pin-${label.toLowerCase()}">${label}</div>`, iconSize: [26, 26], iconAnchor: [13, 13] });

export function showRoute(route, from, to) {
  routeLayer.clearLayers();
  if (route) {
    const latlngs = route.coords.map(([x, y]) => [y, x]);
    routeLayer.addLayer(L.polyline(latlngs, { renderer: sel, interactive: false, color: "#ffffff", weight: 10, opacity: 0.95, lineCap: "round", lineJoin: "round" }));
    routeLayer.addLayer(L.polyline(latlngs, { renderer: sel, interactive: false, color: ACCENT, weight: 6, opacity: 1, lineCap: "round", lineJoin: "round" }));
    fitTo(L.latLngBounds(latlngs), 17);
  }
  if (from) routeLayer.addLayer(L.marker([from.lat, from.lon], { icon: pinIcon("A"), interactive: false }));
  if (to) routeLayer.addLayer(L.marker([to.lat, to.lon], { icon: pinIcon("B"), interactive: false }));
}

// Where the person is, once they ask.
const meLayer = L.layerGroup().addTo(map);
export function showMe(lat, lon, fly = true) {
  meLayer.clearLayers();
  meLayer.addLayer(L.circleMarker([lat, lon], { renderer: sel, interactive: false, radius: 16, stroke: false, fillColor: ACCENT, fillOpacity: 0.18 }));
  meLayer.addLayer(L.circleMarker([lat, lon], { renderer: sel, interactive: false, radius: 7, color: "#fff", weight: 2.5, fillColor: ACCENT, fillOpacity: 1 }));
  if (fly) centerOn([lat, lon], Math.max(map.getZoom(), 17));
}

export function flashStep(lat, lng) {
  centerOn([lat, lng], Math.max(map.getZoom(), 17));
}

// ---------- clicks on empty map ----------
map.on("click", e => {
  if (handlers.pick?.(e.latlng)) return;
  const c = communeAt(e.latlng.lat, e.latlng.lng);
  if (c) emit("commune", c, e.latlng);
});

// Right-click or long-press anywhere, on a building or street too: what is the address here?
map.getContainer().addEventListener("contextmenu", e => {
  e.preventDefault();
  emit("here", map.mouseEventToLatLng(e));
});

export function langChanged() {
  labels.redraw();
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

export { lang };
