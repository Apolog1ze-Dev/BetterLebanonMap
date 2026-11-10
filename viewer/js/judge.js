// The access judge's approval queue: the model's least confident answers, one house at a time, on
// the satellite photo and the OSM map side by side, for a person to approve, correct or reject.

const LETTERS = "ABCD";
const COLORS = ["#1e90ff", "#ff8c00", "#ba55d3", "#2ecc71"];
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

const sat = L.map("sat", { zoomControl: true, maxZoom: 20 });
const osm = L.map("osm", { zoomControl: false, maxZoom: 20 });
L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  { maxNativeZoom: 19, maxZoom: 20, attribution: "Imagery © Esri" }).addTo(sat);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  { maxNativeZoom: 19, maxZoom: 20, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(osm);
const layers = [L.layerGroup().addTo(sat), L.layerGroup().addTo(osm)];

// The two maps move together.
let syncing = false;
for (const [a, b] of [[sat, osm], [osm, sat]]) {
  a.on("move", () => {
    if (syncing) return;
    syncing = true;
    b.setView(a.getCenter(), a.getZoom(), { animate: false });
    syncing = false;
  });
}

let items = [], current = null;

async function load() {
  const r = await fetch("/api/judge/queue?n=20");
  const doc = await r.json();
  items = doc.items;
  showStats(doc.stats);
  next();
}

function showStats(s) {
  const by = s.by_status ?? {};
  $("#stats").textContent = `${s.queue.toLocaleString()} waiting · ${s.judged.toLocaleString()} of ${s.planned.toLocaleString()} houses judged · `
    + `${(by.auto ?? 0).toLocaleString()} applied automatically · ${((by.approved ?? 0) + (by.corrected ?? 0)).toLocaleString()} approved by you`;
}

function next() {
  current = items.shift() ?? null;
  for (const g of layers) g.clearLayers();
  if (!current) {
    $("#side").innerHTML = `<div class="empty"><h2>Nothing waiting</h2><p class="muted">Run the judge to fill the queue:</p>
      <p><code>uv run python -I -m better_lebanon_map.judge run</code></p></div>`;
    return;
  }
  draw(current);
  side(current);
}

function draw(it) {
  const c = it.context, ll = ([x, y]) => [y, x];
  const bounds = L.latLngBounds([ll(c.point)]);
  for (const [k, g] of layers.entries()) {
    c.candidates.forEach((cand, n) => {
      for (const line of cand.lines) g.addLayer(L.polyline(line.map(ll), { color: COLORS[n], weight: k ? 6 : 4, opacity: 0.9 }));
      g.addLayer(L.circleMarker(ll(cand.junction), { radius: 11, color: "#fff", weight: 2, fillColor: COLORS[n], fillOpacity: 1 })
        .bindTooltip(LETTERS[n], { permanent: true, direction: "center", className: "letter" }));
      bounds.extend(ll(cand.junction));
    });
    g.addLayer(L.polygon(c.house.map(ll), { color: "#d93025", weight: 3, fillOpacity: k ? 0.35 : 0.1 }));
    const p = LETTERS.indexOf(it.choice);
    if (p >= 0) g.addLayer(L.polyline([ll(c.candidates[p].junction), ll(c.point)], { color: "#d93025", weight: 3, dashArray: "7 6" }));
  }
  sat.fitBounds(bounds.pad(0.35), { maxZoom: 19, animate: false });
}

function names(cand) {
  return `<span class="names"><span>${esc(cand.name_fr ?? "(unnamed street)")}</span>`
    + (cand.name_ar ? `<span class="ar muted" lang="ar">${esc(cand.name_ar)}</span>` : "") + `</span>`;
}

function side(it) {
  const c = it.context, p = LETTERS.indexOf(it.choice);
  const proposal = p >= 0
    ? `<span class="chip" style="background:${COLORS[p]}">${LETTERS[p]}</span>${esc(c.candidates[p].name_fr ?? "(unnamed street)")}`
    : `<b>None</b> of the candidates`;
  $("#side").innerHTML = `
    <h2>House ${esc(it.key)}</h2>
    <div class="muted">${it.distance.toFixed(0)} m from the nearest street ·
      <a href="https://www.openstreetmap.org/${it.key[0] === "w" ? "way" : "relation"}/${esc(it.key.slice(1))}" target="_blank" rel="noopener">OSM</a></div>
    <div class="proposal">
      <div class="muted">The model proposes (${esc(it.model)}, confidence ${Math.round(it.confidence ?? 0)})</div>
      <div style="margin:4px 0">${proposal}</div>
      <div class="muted">${esc(it.reason)}</div>
    </div>
    <div class="muted">Reached from:</div>
    <ol class="cands">${c.candidates.map((cand, n) => `<li><button data-letter="${LETTERS[n]}" class="${n === p ? "proposed" : ""}">
      <span class="chip" style="background:${COLORS[n]}">${LETTERS[n]}</span>${names(cand)}
      <span class="muted" style="margin-left:auto">${cand.dist.toFixed(0)} m</span></button></li>`).join("")}</ol>
    <div class="actions">
      <button class="primary" data-action="approve" ${p < 0 ? "disabled" : ""}>Approve <kbd>Enter</kbd></button>
      <button data-action="none">None visible <kbd>N</kbd></button>
      <button data-action="skip">Skip <kbd>S</kbd></button>
    </div>
    <p class="muted">Pick a street with <kbd>A</kbd>–<kbd>${LETTERS[c.candidates.length - 1]}</kbd> when the model is wrong.
      Approved and corrected houses take that street at the next pipeline run.</p>`;
}

async function decide(action, letter) {
  if (!current) return;
  const r = await fetch("/api/judge/decide", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key: current.key, action, letter }) });
  const doc = await r.json();
  if (doc.stats) showStats(doc.stats);
  if (!items.length) return load();
  next();
}

$("#side").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b || b.disabled) return;
  if (b.dataset.letter) decide("choose", b.dataset.letter);
  else if (b.dataset.action) decide(b.dataset.action);
});
document.addEventListener("keydown", e => {
  if (e.target.closest("input, textarea") || !current) return;
  const k = e.key.toUpperCase();
  if (k === "ENTER" && LETTERS.includes(current.choice)) decide("approve");
  else if (k === "N") decide("none");
  else if (k === "S") decide("skip");
  else if (LETTERS.slice(0, current.context.candidates.length).includes(k)) decide("choose", k);
});

const style = document.createElement("style");
style.textContent = ".leaflet-tooltip.letter{background:none;border:0;box-shadow:none;color:#fff;font-weight:700;font-size:12px;padding:0}"
  + ".leaflet-tooltip.letter:before{display:none}";
document.head.appendChild(style);
load();
