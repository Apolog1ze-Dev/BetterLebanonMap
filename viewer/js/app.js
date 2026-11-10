// Interface wiring: search, info cards, directions, map controls, language and shareable links.
//
// <body data-view> says what the card shows: "home" (the welcome, nothing selected), "card" (the
// thing selected) or "directions". On a desktop the bar (search) and the sheet (card) are one
// floating card; on a phone the bar floats at the top and the sheet slides up from the bottom.

import { distance, duration, lang, num, pick, setLang, t } from "./i18n.js";
import * as mv from "./mapview.js";
import { route } from "./router.js";
import { describe, placeName, resolveAddress, search, spotOn, warmUp } from "./search.js";
import { SRC, communeAt, loadBase, loadBuildings, loadCommune, loadPois, loadSearch, nearestAddress, store, streetById } from "./store.js";
import { copyText, debounce, esc, projectOnLine } from "./util.js";

const $ = sel => document.querySelector(sel);
const initialHash = location.hash;   // read before the map's first move rewrites it
let restored = false;
const card = $("#card");
let currentCard = null;   // () => html, re-rendered on language change

// ---------- icons ----------
const ICONS = {
  pin: '<path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.500C5 14.800 12 21 12 21Z"/><circle cx="12" cy="9.500" r="2.500"/>',
  road: '<path d="M8 3 5 21M16 3l3 18M12 4v3M12 10.500v3M12 17v3"/>',
  town: '<path d="M4 20V9l6-3v14M10 20V4l10 4v12M3 20h18M14 11h2M14 15h2"/>',
  store: '<path d="M4 10v10h16V10M3 10l2-6h14l2 6M10 20v-5h4v5"/>',
  cross: '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M12 8.500v7M8.500 12h7"/>',
  cap: '<path d="M3 9l9-4.500L21 9l-9 4.500L3 9Z"/><path d="M7 11.500V16c1.500 1.300 3.200 2 5 2s3.500-.700 5-2v-4.500"/>',
  shield: '<path d="M12 3l7 3v5c0 4.500-3 8-7 10-4-2-7-5.500-7-10V6l7-3Z"/>',
  fuel: '<path d="M5 20V6a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2v14M4 20h11M7 9h5M14 11h2a2 2 0 0 1 2 2v3a1.500 1.500 0 0 0 3 0V9l-3-3"/>',
  bank: '<path d="M3 10l9-6 9 6M5 10v8M9.500 10v8M14.500 10v8M19 10v8M3 20h18"/>',
  food: '<path d="M7 3v8M5 3v5a2 2 0 0 0 4 0V3M7 11v10M17 3c-2 2-3 4.500-3 7.500h3m0-7.500v18"/>',
  bed: '<path d="M3 18v-8m0 4h18m0 4v-6a3 3 0 0 0-3-3h-8v5M6.500 11.500h.010"/>',
  star: '<path d="M12 4l2.400 5 5.600.700-4.100 3.800 1.100 5.500-5-2.800-5 2.800 1.100-5.500L4 9.700 9.600 9 12 4Z"/>',
  tree: '<path d="M12 21v-6M12 15c-3.500 0-6-2.300-6-5.500S8.500 3 12 3s6 3.200 6 6.500-2.500 5.500-6 5.500Z"/>',
  building: '<path d="M6 21V4h12v17M3 21h18M10 8h1M13 8h1M10 12h1M13 12h1M10 16h4v5"/>',
  dome: '<path d="M4 21v-7a8 8 0 0 1 16 0v7M3 21h18M12 3v3M10 21v-4a2 2 0 0 1 4 0v4"/>',
  search: '<circle cx="11" cy="11" r="6.500"/><path d="M16 16l4.500 4.500"/>',
  locate: '<circle cx="12" cy="12" r="3.200"/><path d="M12 2.500v3M12 18.500v3M2.500 12h3M18.500 12h3"/>',
  directions: '<path d="M12 3l9 9-9 9-9-9z"/><path d="M9 14.500V12a1.500 1.500 0 0 1 1.500-1.500H15m0 0-2-2m2 2-2 2"/>',
  share: '<path d="M12 15V4m0 0L8 8m4-4 4 4M5 12v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2.500"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
  check: '<path d="M5 12.500l4.500 4.500L19 7.500"/>',
  dashed: '<circle cx="12" cy="12" r="8" stroke-dasharray="4 3.500"/>',
  chevron: '<path d="M9 6l6 6-6 6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.010"/>',
  straight: '<path d="M12 20V5m0 0-5 5m5-5 5 5"/>',
  slight_left: '<path d="M15 20v-6L8 7m0 0v5m0-5h5"/>',
  slight_right: '<path d="M9 20v-6l7-7m0 0v5m0-5h-5"/>',
  turn_left: '<path d="M17 20v-7a4 4 0 0 0-4-4H6m0 0 4-4M6 9l4 4"/>',
  turn_right: '<path d="M7 20v-7a4 4 0 0 1 4-4h7m0 0-4-4m4 4-4 4"/>',
  uturn: '<path d="M7 20V9a5 5 0 0 1 10 0v6m0 0-3-3m3 3 3-3"/>',
  roundabout: '<circle cx="12" cy="11" r="4"/><path d="M12 21v-6M16 11h4m0 0-2-2m2 2-2 2"/>',
};
const icon = (name, flip = false) => `<svg class="ic${flip ? " flip" : ""}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] ?? ICONS.pin}</svg>`;
// The icon of each kind of place (pois.CATEGORIES): place, worship, school, health, pharmacy, fuel,
// bank, shop, food, hotel, public, leisure, sight, building, office.
const CAT_ICON = ["pin", "dome", "cap", "cross", "cross", "fuel", "bank", "store", "food", "bed", "shield", "tree", "star", "building", "building"];
const TURN_ICON = { depart: "straight", continue: "straight", sharp_left: "turn_left", sharp_right: "turn_right", arrive: "pin" };
const resultIcon = r => (r.type === "poi" ? CAT_ICON[r.p.cat] : { address: "pin", street: "road", commune: "town", place: "pin" }[r.type]);

// ---------- static texts ----------
function applyTexts() {
  document.querySelectorAll("[data-t]").forEach(el => { el.textContent = t(el.dataset.t); });
  document.querySelectorAll("[data-tp]").forEach(el => { el.placeholder = t(el.dataset.tp); });
  document.querySelectorAll("[data-ta]").forEach(el => { el.setAttribute("aria-label", t(el.dataset.ta)); });
  document.querySelectorAll("[data-tt]").forEach(el => { el.title = t(el.dataset.tt); el.setAttribute("aria-label", t(el.dataset.tt)); });
  document.querySelectorAll("[data-lang]").forEach(b => {
    b.classList.toggle("on", b.dataset.lang === lang());
    b.setAttribute("aria-pressed", b.dataset.lang === lang());
  });
  $("#lang-cycle").textContent = { en: "EN", fr: "FR", ar: "ع" }[lang()];
  document.title = t("title");
}

// ---------- names and addresses ----------
const communeName = c => pick([c.ar, c.fr, c.en]);
const districtName = c => {
  const d = c.d >= 0 ? store.districts[c.d] : store.governorates[c.g];
  return d ? pick([d.ar, d.fr, d.en]) : "";
};
const fullAddress = (num, s, c, l = lang()) => {
  const [ar, fr, en] = s.names;
  if (l === "ar") return `${ar}، رقم ${num}، ${c.ar}`;
  if (l === "en") return `${num} ${en}, ${c.en}`;
  return `${num} ${fr}, ${c.fr}`;
};
const LANGS = ["ar", "fr", "en"];
const langAttrs = l => (l === "ar" ? 'lang="ar" dir="rtl"' : `lang="${l}" dir="ltr"`);

// ---------- views ----------
function setView(name) {
  if (document.body.dataset.view === "directions" && name !== "directions") mv.showRoute(null);
  document.body.dataset.view = name;
  $("#view-explore").hidden = name === "directions";
  $("#view-directions").hidden = name !== "directions";
  openPanel();
}

// home: the card is the welcome (nothing is selected). The search box names what is selected.
function show(render, home = false) {
  currentCard = render;
  card.innerHTML = render();
  if (!home && selected) {
    $("#q").value = selectedLabel();
    $("#clear").hidden = false;
  }
  setView(home ? "home" : "card");
  $(".scroll").scrollTop = 0;
}

// ---------- card pieces ----------
// A street's name as its sign: in Arabic and in the Latin script of the language shown (French
// beside Arabic), with the house number when there is one. approx: a number no building has.
function plaque(s, number = null, approx = false) {
  const [ar, fr, en] = s.names, arabic = lang() === "ar";
  const main = `<h2>${esc(arabic ? ar : lang() === "en" ? en : fr)}</h2>`;
  const other = `<div class="other" ${langAttrs(arabic ? "fr" : "ar")}>${esc(arabic ? fr : ar)}</div>`;
  const n = number === null ? "" : `<div class="plaque-num${String(number).length > 3 ? " long" : ""}">${esc(number)}</div>`;
  return `<div class="plaque${approx ? " approx" : ""}"><div class="plaque-in">${n}<div class="plaque-names">${arabic ? main + other : other + main}</div></div></div>`;
}

const badge = kind => `<span class="badge ${kind}">${icon(kind === "ok" ? "check" : "dashed")}${esc(t(kind === "ok" ? "exact_badge" : "approx_badge"))}</span>`;
const whereLine = (c, extra = "") => `<div class="where"><span class="town">${esc(communeName(c))} <span>· ${esc(districtName(c))}</span></span>${extra}</div>`;
const pointActions = () => `<div class="actions">
      <button type="button" class="btn primary" data-act="to">${icon("directions")}${esc(t("tile_dir"))}</button>
      <button type="button" class="btn" data-act="share">${icon("share")}${esc(t("share"))}</button>
      <button type="button" class="btn" data-act="copy" aria-label="${esc(t("copy"))}">${icon("copy")}<span class="label">${esc(t("copy"))}</span></button>
    </div>`;
const onStreet = (n, street) => `<div class="onstreet"><span class="round-ic">${icon("road")}</span>
      <div><b>${esc(t("onstreet", { n, street }))}</b>${esc(t(n % 2 ? "onstreet_left" : "onstreet_right"))}
      <span class="small">${esc(t("sides_rule"))}</span></div></div>`;
// The address in the languages the card is not shown in, each with its own copy button.
const langRows = (n, s, c) => `<div class="lang-rows">${LANGS.filter(l => l !== lang()).map(l => `<div class="lang-row">
      <span class="code">${l.toUpperCase()}</span><span class="text" ${langAttrs(l)}>${esc(fullAddress(n, s, c, l))}</span>
      <button type="button" class="bar-btn" data-act="copy-lang" data-l="${l}" aria-label="${esc(t("copy"))} ${l.toUpperCase()}">${icon("copy")}</button>
    </div>`).join("")}</div>`;
const reportLink = label => (store.site.repo ? `<a href="https://github.com/${esc(store.site.repo)}/issues/new?title=${encodeURIComponent(label)}" target="_blank" rel="noopener">${esc(t("report"))}</a>` : "");

function welcome() {
  const ex = store.example;
  const tryRow = (name, text, kind) => `<li><button type="button" data-act="try" data-q="${esc(text)}">
        <span class="round-ic">${icon(name)}</span><span class="main">${esc(text)}</span><span class="kind">${esc(t(kind))}</span></button></li>`;
  return `<div class="card home">
    <h1 class="phone-title">${esc(t("home_title"))}</h1>
    <div class="tiles">
      <button type="button" class="tile" data-act="me"><span class="tile-ic">${icon("locate")}</span><b>${esc(t("tile_me"))}</b>
        <span class="sub"><span class="long">${esc(t("tile_me_sub"))}</span><span class="short">${esc(t("tile_me_short"))}</span></span></button>
      <button type="button" class="tile" data-act="directions"><span class="tile-ic">${icon("directions")}</span><b>${esc(t("tile_dir"))}</b>
        <span class="sub"><span class="long">${esc(t("tile_dir_sub"))}</span><span class="short">${esc(t("tile_dir_short"))}</span></span></button>
    </div>
    <div class="try"><div class="eyebrow">${esc(t("try_title"))}</div><ul>
      ${ex ? tryRow("pin", fullAddress(ex.num, ex.s, ex.c), "r_address") : ""}
      ${tryRow("cross", "Pharmacie Bikfaya", "r_poi")}
      ${tryRow("town", t("try_town"), "r_commune")}
    </ul></div>
    <details class="info"><summary>${icon("info")}<span>${esc(t("how_line"))} <span class="how-link">${esc(t("how_link"))}</span></span></summary>
      <ul>
        <li><b class="chip odd">137</b> <b class="chip even">142</b> ${esc(t("howto_sides"))}</li>
        <li>${esc(t("howto_branch"))}</li>
        <li>${esc(t("howto_theme"))}</li>
        <li>${esc(t("howto_here"))}</li>
      </ul></details>
    <p class="fineprint">${esc(t("not_official"))}</p>
  </div>`;
}

// How a house reached by a driveway was matched to its street (access.KINDS).
const ACCESS_NOTE = { 1: "access_drawn", 2: "access_imagery", 3: "access_judged", 4: "access_approved", 5: "access_mapped",
  6: "access_chosen" };

// shown: the address the building is shown under, {s, c, num}; all: every address it has, its
// own (on the nearest street) first, then its aliases on the other streets it may be reached from.
function addressCard(a, shown, all, note) {
  const { s, c } = shown, street = pick(s.names);
  const others = all.filter(x => x !== shown);
  return `<div class="card">
    ${plaque(s, shown.num)}
    ${whereLine(c, badge("ok"))}
    ${note ? `<p class="note">${esc(note)}</p>` : ""}
    ${pointActions()}
    ${onStreet(shown.num, street)}
    ${a.access ? `<p class="note">${esc(t(ACCESS_NOTE[a.access[0]], { street }))}</p>` : ""}
    ${langRows(shown.num, s, c)}
    ${all.length > 1 ? `<div class="box">
      <h3>${esc(t("entrance_title"))}</h3>
      <p>${esc(t("entrance_body"))}</p>
      <ul class="also-list">${others.map(x => `<li><a href="#" data-act="as" data-sid="${x.s.sid}">${esc(fullAddress(x.num, x.s, x.c))}</a></li>`).join("")}</ul>
      <p class="ask">${esc(t("entrance_ask"))}</p>
      <div class="choices">${all.map(x => `<button type="button" class="choice" data-act="confirm" data-sid="${x.s.sid}">${esc(pick(x.s.names))}</button>`).join("")}</div>
      <p class="status" role="status" hidden></p>
    </div>` : ""}
    <div class="links"><a href="#" data-act="street">${esc(t("about_street", { street }))}</a>
      ${reportLink(fullAddress(shown.num, s, c, "fr"))}
      <a href="https://www.openstreetmap.org/${a.key[0] === "w" ? "way" : "relation"}/${a.key.slice(1)}" target="_blank" rel="noopener">${esc(t("on_osm"))}</a></div>
  </div>`;
}

// A number no building has, at its distance along the street.
function spotCard(s, c, spot, nearest) {
  const street = pick(s.names), n = spot.num;
  return `<div class="card">
    ${plaque(s, n, true)}
    ${whereLine(c, badge("approx"))}
    <div class="box warn">
      <h3>${esc(t("spot_title", { n }))}</h3>
      <p>${esc(t("spot_explain", { n, street, side: t(spot.side ? "side_right" : "side_left") }))}</p>
    </div>
    ${nearest === null ? "" : `<div class="eyebrow section-title">${esc(t("closest_title"))}</div>
    <button type="button" class="row-link" data-act="number" data-n="${nearest}">
      <b class="chip big ${nearest % 2 ? "odd" : "even"}">${nearest}</b>
      <span class="r-text"><span class="main">${esc(nearest)} ${esc(street)}</span>
        <span class="sub">${esc(t(nearest % 2 === n % 2 ? "same_side" : "other_side"))} · ${esc(t(nearest < n ? "closest_before" : "closest_after", { d: distance(Math.abs(n - nearest)) }))}</span></span>
      ${icon("chevron", true)}</button>`}
    ${pointActions()}
    <div class="links"><a href="#" data-act="street">${esc(t("about_street", { street }))}</a>${reportLink(fullAddress(n, s, c, "fr"))}</div>
  </div>`;
}

// A named place, with the address of the building it is in or nearest to.
function poiCard(p, c, near) {
  const shown = placeName(p);
  const names = [...new Set(p.names.filter(n => n && n !== shown))];
  return `<div class="card">
    <div class="place-head"><span class="round-ic">${icon(CAT_ICON[p.cat])}</span>
      <div><div class="eyebrow">${esc(t(`cat_${p.cat}`))}</div><h2>${esc(shown)}</h2></div></div>
    ${c ? whereLine(c) : ""}
    ${names.length ? `<ul class="names">${names.map(n => `<li dir="auto">${esc(n)}</li>`).join("")}</ul>` : ""}
    <div class="eyebrow section-title">${esc(t("poi_at"))}</div>
    ${near ? `<button type="button" class="row-link" data-act="poi-address">
      <b class="chip big ${near.a.num % 2 ? "odd" : "even"}">${near.a.num}</b>
      <span class="r-text"><span class="main">${esc(fullAddress(near.a.num, near.s, near.c))}</span><span class="sub">${esc(distance(near.dist))}</span></span>
      ${icon("chevron", true)}</button>` : `<p class="muted">${esc(t("nothing_here"))}</p>`}
    <div class="actions">
      <button type="button" class="btn primary" data-act="to">${icon("directions")}${esc(t("tile_dir"))}</button>
      <button type="button" class="btn" data-act="share">${icon("share")}${esc(t("share"))}</button>
    </div>
  </div>`;
}

function explain(s, c) {
  const [, ...rest] = (s.ref ?? "").split("/");
  switch (SRC[s.src]) {
    case "osm": return t("src_osm");
    case "landmark": return t("src_landmark");
    case "place": return t("src_place");
    case "destination": {
      const to = store.communeById.get(rest[0]);
      return t("src_destination", { to: to ? communeName(to) : "" });
    }
    case "theme": return t("src_theme", { commune: communeName(c), theme: t(`theme_${rest[0]}`) });
    case "branch": {
      const parent = store.streetNames?.get(+rest[0]);
      return t("src_branch", { parent: parent ? pick(parent.names) : "", n: rest[1], side: t(rest[2] === "left" ? "side_left" : "side_right") });
    }
    default: return t("src_systematic");
  }
}

function streetCard(s, c, note) {
  const parentSid = SRC[s.src] === "branch" ? +s.ref.split("/")[1] : null;
  return `<div class="card">
    ${plaque(s)}
    ${whereLine(c)}
    ${note ? `<p class="note flag">${esc(note)}</p>` : ""}
    <div class="facts">
      <span>${esc(t("houses", { n: num(s.addrs.length) }))}</span>
      <span>${esc(t("length", { d: distance(s.len) }))}</span>
      ${s.odd ? `<span class="side odd">${esc(t("odd_range", { a: s.odd[0], b: s.odd[1] }))}</span>` : ""}
      ${s.even ? `<span class="side even">${esc(t("even_range", { a: s.even[0], b: s.even[1] }))}</span>` : ""}
    </div>
    <div class="actions">
      <button type="button" class="btn primary" data-act="fit">${esc(t("show_street"))}</button>
      ${parentSid !== null ? `<button type="button" class="btn" data-act="parent">${esc(pick(store.streetNames?.get(parentSid)?.names))}</button>` : ""}
      <button type="button" class="btn" data-act="share">${icon("share")}${esc(t("share"))}</button>
    </div>
    <details class="more"><summary>${esc(t("why_name"))}</summary>
      <p>${esc(explain(s, c))}</p>
      ${s.old ? `<p>${esc(t("formerly", { old: s.old }))}</p>` : ""}
      ${s.review === 1 ? `<p class="flag">${esc(t("review"))}</p>` : ""}
      ${s.review === 2 ? `<p>${esc(t("transcribed"))}</p>` : ""}
      <ul class="names">${LANGS.map((l, i) => `<li ${langAttrs(l)}>${esc(s.names[i])}</li>`).join("")}</ul>
      <p>${esc(t("street_start"))}: ● 0</p>
    </details>
  </div>`;
}

function communeCard(c) {
  const kind = ["kind_city", "kind_town", "kind_village", "kind_quarter"][c.kind];
  const gov = store.governorates[c.g], names = [c.ar, c.fr, c.en];
  return `<div class="card plain">
    <div class="eyebrow">${esc(t(kind))}</div>
    <h2>${esc(communeName(c))}</h2>
    <div class="where"><span class="town">${esc(districtName(c))}${gov && c.d >= 0 ? ` <span>· ${esc(pick([gov.ar, gov.fr, gov.en]))}</span>` : ""}</span></div>
    <ul class="names">${LANGS.map((l, i) => (names[i] === communeName(c) ? "" : `<li ${langAttrs(l)}>${esc(names[i])}</li>`)).join("")}</ul>
    <div class="facts">
      <span>${esc(t("streets_n", { n: num(c.streets) }))}</span><span>${esc(t("addresses_n", { n: num(c.addr) }))}</span>
      ${c.pop ? `<span>${esc(t("population", { n: num(c.pop) }))}</span>` : ""}<span>${esc(t("area", { n: num(c.area) }))}</span>
    </div>
    <div class="actions"><button type="button" class="btn primary" data-act="fit">${esc(t("show_commune"))}</button>
      <button type="button" class="btn" data-act="share">${icon("share")}${esc(t("share"))}</button></div>
    <details class="more"><summary>${esc(t("boundary_title"))}</summary>
      <p class="${c.est ? "flag" : ""}">${esc(t(c.est ? "border_est" : "border_osm"))}</p>
      ${c.cont >= 0.01 ? `<p class="flag">${esc(t("contested_note", { n: num(c.cont) }))}</p>` : ""}
    </details>
  </div>`;
}

const messageCard = key => () => `<div class="card plain"><p>${esc(t(key))}</p></div>`;

// ---------- selecting things ----------
let selected = null;   // {type, ...} for links and language changes

// as: the street id of the alias to show the building under, instead of its own address.
async function selectAddress(a, { fly = false, note = null, as = null } = {}) {
  const data = await loadCommune(a.commune);
  await loadSearch();
  const entry = (s, n) => s && { s, c: store.communeById.get(s.commune), num: n };
  const all = [entry(data.streetById.get(a.sid), a.num),
    ...await Promise.all(a.also.map(async ([sid, n]) => entry(await streetById(sid), n)))].filter(Boolean);
  const shown = all.find(x => x.s.sid === as) ?? all[0];
  const buildings = await loadBuildings(a.commune);
  const b = buildings.find(x => x.addr === a.i);
  selected = { type: "address", a, all, s: shown.s, c: shown.c, num: shown.num, lat: a.lat, lon: a.lon };
  show(() => addressCard(a, shown, all, note));
  mv.highlightAddress(a, b?.ring, fly, shown.num);
  updateHash();
}

async function selectSpot(s, spot, nearest, fly = true) {
  await loadSearch();
  const c = store.communeById.get(s.commune);
  selected = { type: "spot", s, c, num: spot.num, lat: spot.lat, lon: spot.lon };
  show(() => spotCard(s, c, spot, nearest));
  mv.highlightSpot(spot.lat, spot.lon, fly, spot.num);
  updateHash();
}

async function selectPoi(p, fly = true) {
  const found = await nearestAddress(p.lat, p.lon, 100);
  let near = null;
  if (found) {
    const s = (await loadCommune(found.address.commune)).streetById.get(found.address.sid);
    near = { a: found.address, s, c: store.communeById.get(s.commune), dist: found.dist };
  }
  selected = { type: "poi", p, near, lat: p.lat, lon: p.lon };
  show(() => poiCard(p, communeAt(p.lat, p.lon), near));
  mv.highlightSpot(p.lat, p.lon, fly);
  updateHash();
}

// An address result: its building, or the spot of a number no building has, or the street when
// the number is past its end.
async function selectResolved(res, number) {
  if (res.address) return selectAddress(res.address, { fly: true, as: res.as?.s.sid });
  if (res.spot) return selectSpot(res.street, res.spot, res.nearest);
  if (res.street) return selectStreet(res.street, true, t("beyond_end", { street: pick(res.street.names), d: distance(res.street.len), n: number }));
}

// The address nearest a point of the map (right-click, long-press, "my address").
async function whatsHere(lat, lon, fly = false) {
  const found = await nearestAddress(lat, lon);
  if (found) return selectAddress(found.address, { fly, note: found.dist > 15 ? t("nearest_here", { d: distance(found.dist) }) : null });
  selected = null;
  show(messageCard("nothing_here"));
  mv.highlightSpot(lat, lon, fly);
}

async function selectStreet(s, fit = false, note = null) {
  await loadSearch();
  const c = store.communeById.get(s.commune);
  selected = { type: "street", s, c };
  show(() => streetCard(s, c, note));
  mv.highlightStreet(s, fit);
  updateHash();
}

function selectCommune(c, fit = false) {
  selected = { type: "commune", c };
  show(() => communeCard(c));
  mv.highlightCommune(c, fit);
  updateHash();
}

function goHome() {
  selected = null;
  mv.clearSelection();
  $("#q").value = "";
  $("#clear").hidden = true;
  show(welcome, true);
  updateHash();
}

mv.on("street", s => selectStreet(s));
mv.on("address", a => selectAddress(a));
mv.on("commune", c => selectCommune(c));
mv.on("building", (b, data) => {
  if (b.addr >= 0) return selectAddress(data.addr[b.addr]);
  mv.clearSelection();
  selected = null;
  show(messageCard("no_address"));
});
mv.on("here", latlng => whatsHere(latlng.lat, latlng.lng));

// What a card's "directions", "copy" and "share" call the thing selected.
const selectedLabel = () => (selected.type === "poi" ? placeName(selected.p)
  : selected.type === "commune" ? communeName(selected.c)
    : selected.type === "street" ? `${pick(selected.s.names)}, ${communeName(selected.c)}`
      : fullAddress(selected.num, selected.s, selected.c));

// "Its entrance is on this street": saved by the local server for the next build
// (data/corrections/streets.jsonl). A copy published on GitHub opens an issue of its repository
// with the correction instead (corrections.py collects them); any other copy puts it on the clipboard.
async function confirmStreet(btn) {
  const { a, all } = selected;
  const { s, c, num: n } = all.find(x => x.s.sid === +btn.dataset.sid);
  const at = s.parts.map(p => projectOnLine(p, a.lon, a.lat)).reduce((x, y) => (y.dist < x.dist ? y : x));
  const doc = { key: a.key, junction: at.point.map(v => +v.toFixed(6)), street: `${s.names[1]}, ${c.fr}` };
  const status = card.querySelector(".status");
  const say = key => { btn.classList.add("done"); status.textContent = t(key); status.hidden = false; syncInsets(); };
  if (store.site.repo) {
    const body = `This building is reached from this street (sent from its address card on the map).\n\n\`\`\`json\n${JSON.stringify(doc)}\n\`\`\`\n`;
    window.open(`https://github.com/${store.site.repo}/issues/new?title=${encodeURIComponent(`Access: ${fullAddress(n, s, c, "fr")}`)}&body=${encodeURIComponent(body)}`, "_blank", "noopener");
    return say("confirm_issue");
  }
  let saved = false;
  try {
    saved = (await fetch("api/access/choose", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(doc) })).ok;
  } catch { /* no server behind the map */ }
  if (saved) say("confirm_saved");
  else if (await copyText(JSON.stringify(doc))) say("confirm_copied");
}

async function share(btn) {
  const text = selectedLabel();
  if (navigator.share) {
    try { return await navigator.share({ title: t("title"), text, url: location.href }); } catch (e) { if (e.name === "AbortError") return; }
  }
  flash(btn, (await copyText(location.href)) ? t("link_copied") : "✕");
}

card.addEventListener("click", async e => {
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  e.preventDefault();
  const act = btn.dataset.act;
  if (act === "me") return myAddress(btn);
  if (act === "directions") return openDirections();
  if (act === "try") return trySearch(btn.dataset.q);
  if (!selected) return;
  if (act === "copy") {
    flash(btn, (await copyText(selectedLabel())) ? t("copied") : "✕");
  } else if (act === "copy-lang") {
    flash(btn, (await copyText(fullAddress(selected.num, selected.s, selected.c, btn.dataset.l))) ? icon("check") : "✕", 1400, true);
  } else if (act === "share") {
    share(btn);
  } else if (act === "to") {
    setEndpoint("to", { lat: selected.lat, lon: selected.lon, sid: (selected.s ?? selected.near?.s)?.sid, label: selectedLabel() });
    openDirections();
  } else if (act === "as") {
    selectAddress(selected.a, { as: +btn.dataset.sid });
  } else if (act === "confirm") {
    confirmStreet(btn);
  } else if (act === "number") {
    const s = selected.s, n = +btn.dataset.n;
    selectResolved(await resolveAddress({ s: { c: store.communeById.get(s.commune).idx, sid: s.sid }, number: n }), n);
  } else if (act === "poi-address") {
    selectAddress(selected.near.a, { fly: true });
  } else if (act === "street") {
    selectStreet(selected.s, true);
  } else if (act === "fit" && selected.type === "street") {
    mv.highlightStreet(selected.s, true);
  } else if (act === "fit" && selected.type === "commune") {
    mv.highlightCommune(selected.c, true);
  } else if (act === "parent") {
    const parent = await streetById(+selected.s.ref.split("/")[1]);
    if (parent) selectStreet(parent, true);
  }
});

function flash(btn, text, ms = 1400, html = false) {
  const old = btn.innerHTML;
  if (html) btn.innerHTML = text; else btn.textContent = text;
  setTimeout(() => { btn.innerHTML = old; }, ms);
}

function toast(text) {
  document.querySelector(".toast")?.remove();
  const el = Object.assign(document.createElement("div"), { className: "toast", textContent: text });
  el.setAttribute("role", "status");
  document.body.append(el);
  setTimeout(() => el.remove(), 4500);
}

// Where the person is: resolves to {lat, lon}, or null (with a word of why) when the browser cannot say.
function whereAmI(busyEl) {
  return new Promise(resolve => {
    if (!navigator.geolocation) { toast(t("no_location")); return resolve(null); }
    busyEl?.classList.add("busy");
    navigator.geolocation.getCurrentPosition(
      p => { busyEl?.classList.remove("busy"); resolve({ lat: p.coords.latitude, lon: p.coords.longitude }); },
      () => { busyEl?.classList.remove("busy"); toast(t("no_location")); resolve(null); },
      { enableHighAccuracy: true, timeout: 15000 });
  });
}

async function myAddress(btn) {
  const me = await whereAmI(btn);
  if (!me) return;
  mv.showMe(me.lat, me.lon, false);
  whatsHere(me.lat, me.lon, true);
}

// ---------- search boxes ----------
// One result row; rows are grouped by kind (towns, streets, addresses, places), best kind first.
function resultRow(r, i, active) {
  const [main, place] = describe(r);
  const sub = r.type === "poi" ? [t(`cat_${r.p.cat}`), place].filter(Boolean).join(" · ") : place;
  return `<li role="option" data-i="${i}" class="${i === active ? "on" : ""}" aria-selected="${i === active}"><span class="r-ic">${icon(resultIcon(r))}</span>
    <span class="r-text"><span class="main">${esc(main)}</span><span class="sub">${esc(sub)}</span></span></li>`;
}

// inline: the list is part of the card and takes the place of what the card showed.
function attachSearch(input, list, onPick, inline = false) {
  let items = [], active = -1;
  const setOpen = open => {
    list.hidden = !open;
    if (inline) { document.body.classList.toggle("searching", open); syncInsets(); }
  };
  const render = () => {
    setOpen(items.length > 0 || input.value.trim() !== "");
    let kind = null;
    list.innerHTML = items.length ? items.map((r, i) => {
      const head = r.type === kind ? "" : `<li class="group" role="presentation">${esc(t(`r_${r.type}`))}</li>`;
      kind = r.type;
      return head + resultRow(r, i, active);
    }).join("") : `<li class="empty">${esc(input.value.trim() ? t("no_results") : "")}</li>`;
  };
  const run = debounce(async () => {
    const q = input.value;
    if (!q.trim()) { items = []; setOpen(false); return; }
    const res = await search(q, 30);
    if (q !== input.value) return;
    // Kinds in the order of their best result, each kind's rows together: at most four of a kind,
    // nine in all, so that a town's streets do not push its places off the list.
    const kinds = [...new Set(res.map(r => r.type))];
    items = kinds.flatMap(k => res.filter(r => r.type === k).slice(0, 4)).slice(0, 9);
    active = items.length ? 0 : -1;
    render();
  }, 140);
  input.addEventListener("input", run);
  input.addEventListener("focus", () => { warmUp(); if (items.length) setOpen(true); });
  input.addEventListener("keydown", e => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      active = Math.max(0, Math.min(items.length - 1, active + (e.key === "ArrowDown" ? 1 : -1)));
      render();
      list.querySelector(".on")?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter" && items[active]) {
      e.preventDefault();
      choose(items[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  });
  list.addEventListener("mousedown", e => {
    const li = e.target.closest("[data-i]");
    if (li) { e.preventDefault(); choose(items[+li.dataset.i]); }
  });
  input.addEventListener("blur", () => setTimeout(() => setOpen(false), 150));
  const choose = r => { setOpen(false); input.blur(); onPick(r, input); };
  return { clear() { items = []; setOpen(false); } };
}

async function resultToPoint(r) {
  if (r.type === "commune") return { lat: r.c.label[1], lon: r.c.label[0], label: communeName(r.c) };
  if (r.type === "place") return { lat: r.p.lat, lon: r.p.lon, label: pick(r.p.names) };
  if (r.type === "street") {
    const s = await streetById(r.s.sid);
    const mid = s.parts[0][Math.floor(s.parts[0].length / 2)];
    return { lat: mid[1], lon: mid[0], sid: s.sid, label: `${pick(s.names)}, ${communeName(store.communeById.get(s.commune))}` };
  }
  if (r.type === "poi") return { lat: r.p.lat, lon: r.p.lon, label: placeName(r.p) };
  const { street, address, spot } = await resolveAddress(r);
  const at = address ?? spot;
  if (!at) return null;
  return { lat: at.lat, lon: at.lon, sid: street.sid, label: fullAddress(r.number, street, store.communeById.get(street.commune)) };
}

async function openResult(r) {
  if (r.type === "commune") return selectCommune(r.c, true);
  if (r.type === "place") {
    const c = communeAt(r.p.lat, r.p.lon);
    if (c) selectCommune(c);
    return mv.map.setView([r.p.lat, r.p.lon], 16);
  }
  if (r.type === "poi") return selectPoi(r.p);
  if (r.type === "street") {
    const s = await streetById(r.s.sid);
    return s && selectStreet(s, true);
  }
  return selectResolved(await resolveAddress(r), r.number);
}

const q = $("#q");
const mainSearch = attachSearch(q, $("#results"), r => openResult(r), true);
q.addEventListener("input", () => { $("#clear").hidden = !q.value; });
$("#clear").addEventListener("click", () => {
  q.value = "";
  $("#clear").hidden = true;
  mainSearch.clear();
  q.focus();
});
$("#back").addEventListener("click", goHome);

// An example on the welcome card: the search is run as typed and its first result opened.
async function trySearch(text) {
  q.value = text;
  $("#clear").hidden = false;
  const [first] = await search(text, 1);
  if (first) openResult(first);
}

// ---------- directions ----------
const ends = { from: null, to: null };
let mode = "car", picking = null;

function openDirections() {
  setView("directions");
  computeRoute();
  if (!ends.from && !isPhone()) $("#from").focus();
}

function setEndpoint(which, point) {
  ends[which] = point;
  $(`#${which}`).value = point?.label ?? "";
  if (document.body.dataset.view === "directions") computeRoute();
}

for (const which of ["from", "to"]) {
  const input = $(`#${which}`);
  attachSearch(input, input.parentElement.querySelector(".results"), async r => {
    const p = await resultToPoint(r);
    if (p) setEndpoint(which, p);
  });
}

document.querySelectorAll("[data-pick]").forEach(btn => btn.addEventListener("click", () => {
  picking = btn.dataset.pick;
  document.body.classList.add("picking");
  $("#route-out").innerHTML = `<p class="hint">${esc(t("picking"))}</p>`;
  if (isPhone()) closePanel();
}));

mv.on("pick", latlng => {
  if (!picking) return false;
  setEndpoint(picking, { lat: latlng.lat, lon: latlng.lng, label: `${t("my_point")} (${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)})` });
  picking = null;
  document.body.classList.remove("picking");
  openPanel();
  return true;
});

$("#locate").addEventListener("click", async e => {
  const me = await whereAmI(e.currentTarget);
  if (me) { mv.showMe(me.lat, me.lon, false); setEndpoint("from", { ...me, label: t("here") }); }
});

document.querySelectorAll("[data-mode]").forEach(btn => btn.addEventListener("click", () => {
  mode = btn.dataset.mode;
  document.querySelectorAll("[data-mode]").forEach(b => { b.classList.toggle("on", b === btn); b.setAttribute("aria-pressed", b === btn); });
  computeRoute();
}));

$("#swap").addEventListener("click", () => {
  [ends.from, ends.to] = [ends.to, ends.from];
  $("#from").value = ends.from?.label ?? "";
  $("#to").value = ends.to?.label ?? "";
  computeRoute();
});

$("#clear-route").addEventListener("click", () => {
  ends.from = ends.to = null;
  $("#from").value = $("#to").value = "";
  computeRoute();
});

$("#dir-back").addEventListener("click", () => {
  if (selected) setView("card"); else show(welcome, true);
});

let lastRoute = null, routeRun = 0;
async function computeRoute() {
  const run = ++routeRun;
  mv.showRoute(null, ends.from, ends.to);
  $("#eta-car").textContent = $("#eta-foot").textContent = "";
  if (!ends.from || !ends.to) { lastRoute = null; renderRoute(); return; }
  $("#route-out").innerHTML = `<p class="hint">${esc(t("route_loading"))}</p>`;
  const r = await route(ends.from, ends.to, mode);
  if (run !== routeRun) return;
  lastRoute = r;
  renderRoute();
  if (r.error) return;
  mv.showRoute(r, ends.from, ends.to);
  // How long the other way of travelling would take, beside its button.
  $(`#eta-${mode}`).textContent = duration(r.time);
  const other = mode === "car" ? "foot" : "car";
  const alt = await route(ends.from, ends.to, other);
  if (run === routeRun && !alt.error) $(`#eta-${other}`).textContent = duration(alt.time);
}

function renderRoute() {
  const out = $("#route-out");
  if (!lastRoute) out.innerHTML = "";
  else if (lastRoute.error) out.innerHTML = `<p class="flag">${esc(t(lastRoute.error))}</p>`;
  else {
    out.innerHTML = `<div class="route-summary"><span class="time">${esc(duration(lastRoute.time))}</span>
      <span class="dist">${esc(t(mode === "car" ? "by_car" : "on_foot", { d: distance(lastRoute.distance) }))}</span></div>
    <ol class="steps">${lastRoute.steps.map((s, i) => `<li data-i="${i}" class="${s.arrive ? "arrive" : ""}">
      <span class="round-ic">${icon(TURN_ICON[s.turn] ?? s.turn)}</span>
      <span class="txt">${esc(s.text)}</span>${s.dist ? `<span class="d">${esc(distance(s.dist))}</span>` : ""}</li>`).join("")}</ol>`;
  }
  syncInsets();
}

$("#route-out").addEventListener("click", e => {
  const li = e.target.closest("[data-i]");
  if (li && lastRoute?.steps) {
    const s = lastRoute.steps[+li.dataset.i];
    mv.flashStep(s.lat, s.lon);
    if (isPhone()) closePanel();
  }
});

// ---------- map controls ----------
$("#zoom-in").addEventListener("click", () => mv.map.zoomIn());
$("#zoom-out").addEventListener("click", () => mv.map.zoomOut());
$("#show-me").addEventListener("click", async e => {
  const me = await whereAmI(e.currentTarget);
  if (me) mv.showMe(me.lat, me.lon);
});

const stylePop = $("#style-pop"), styleBtn = $("#style-btn");
const setStyleOpen = open => { stylePop.hidden = !open; styleBtn.setAttribute("aria-expanded", open); };
styleBtn.addEventListener("click", () => setStyleOpen(stylePop.hidden));
document.addEventListener("pointerdown", e => {
  if (!stylePop.hidden && !stylePop.contains(e.target) && !styleBtn.contains(e.target)) setStyleOpen(false);
});

document.querySelectorAll("[data-layer]").forEach(cb => cb.addEventListener("change", () => mv.setShow(cb.dataset.layer, cb.checked)));
$("#by-source").addEventListener("change", e => {
  mv.setColorBySource(e.target.checked);
  document.body.classList.toggle("by-source", e.target.checked);
  if (e.target.checked) stylePop.querySelector(".legend-box").open = true;
});
document.querySelectorAll("[name=base]").forEach(r => r.addEventListener("change", () => mv.setBase(r.value)));

// ---------- language ----------
function setLanguage(l) {
  setLang(l);
  applyTexts();
  if (currentCard) card.innerHTML = currentCard();
  if (document.body.dataset.view === "directions") computeRoute();
  mv.langChanged();
  syncInsets();
  updateHash();
}
document.querySelectorAll("[data-lang]").forEach(b => b.addEventListener("click", () => setLanguage(b.dataset.lang)));
$("#lang-cycle").addEventListener("click", () => setLanguage({ en: "fr", fr: "ar", ar: "en" }[lang()]));

// ---------- the sheet, and what of the map the interface hides ----------
const isPhone = () => window.matchMedia("(max-width: 720px)").matches;
function syncInsets() {
  const phone = isPhone(), body = document.body;
  const peek = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--peek")) || 0;
  const visible = !phone || body.classList.contains("searching") ? 0 : body.classList.contains("panel-closed") ? peek : $("#sheet").offsetHeight;
  mv.insets.bottom = visible;
  mv.insets.top = phone ? $("#bar").offsetHeight + 24 : 0;
  mv.insets.start = phone ? 0 : $("#panel").offsetWidth + 16;
  document.documentElement.style.setProperty("--sheet-visible", `${visible}px`);
}
function openPanel() { document.body.classList.remove("panel-closed"); syncInsets(); }
function closePanel() { document.body.classList.add("panel-closed"); syncInsets(); }
$("#grab").addEventListener("click", () => { document.body.classList.toggle("panel-closed"); syncInsets(); });
window.addEventListener("resize", syncInsets);
card.addEventListener("toggle", syncInsets, true);   // a <details> opening changes the sheet's height

// ---------- URL state: #zoom/lat/lng&a=commune:building[&as=alias street] | &s=street[&n=number] | &c=commune | &p=lon,lat ----------
const updateHash = debounce(() => {
  if (!restored) return;
  const c = mv.map.getCenter(), z = mv.map.getZoom();
  let h = `#${z}/${c.lat.toFixed(5)}/${c.lng.toFixed(5)}`;
  if (selected?.type === "address") h += `&a=${selected.a.commune}:${selected.a.key}${selected.s.sid === selected.a.sid ? "" : `&as=${selected.s.sid}`}`;
  else if (selected?.type === "spot") h += `&s=${selected.s.sid}&n=${selected.num}`;
  else if (selected?.type === "poi") h += `&p=${selected.p.lon},${selected.p.lat}`;
  else if (selected?.type === "street") h += `&s=${selected.s.sid}`;
  else if (selected?.type === "commune") h += `&c=${selected.c.id}`;
  h += `&l=${lang()}`;
  lastHash = h;
  history.replaceState(null, "", h);
}, 250);
let lastHash = "";
window.addEventListener("hashchange", () => {
  if (location.hash !== lastHash) restoreHash(location.hash);
});
mv.map.on("moveend", updateHash);

async function restoreHash(hash = initialHash) {
  const [pos, ...params] = hash.slice(1).split("&");
  const [z, lat, lng] = pos.split("/").map(Number);
  if (Number.isFinite(z) && Number.isFinite(lat) && Number.isFinite(lng)) mv.map.setView([lat, lng], z, { animate: false });
  const p = Object.fromEntries(params.map(x => x.split("=")));
  if (p.a) {
    const [cid, key] = p.a.split(":");
    const data = await loadCommune(cid);
    const a = data.addrByKey.get(key);
    if (a) await selectAddress(a, { fly: true, as: p.as ? +p.as : null });
  } else if (p.s) {
    const s = await streetById(+p.s);
    const res = s && p.n ? spotOn(s, +p.n) : null;
    if (res?.spot) await selectSpot(s, res.spot, res.nearest);
    else if (s) await selectStreet(s, !Number.isFinite(z));
  } else if (p.p) {
    const [lon, lat2] = p.p.split(",").map(Number);
    const poi = (await loadPois()).find(x => x.lon === lon && x.lat === lat2);
    if (poi) await selectPoi(poi);
  } else if (p.c) {
    const c = store.communeById.get(p.c);
    if (c) selectCommune(c, !Number.isFinite(z));
  }
}

document.addEventListener("keydown", e => {
  if (e.key === "Escape") setStyleOpen(false);
  if (e.key === "/" && !/^(INPUT|TEXTAREA)$/.test(document.activeElement?.tagName)) {
    e.preventDefault();
    if (document.body.dataset.view === "directions") $("#dir-back").click();
    q.focus();
  }
});

// An address to offer as an example on the welcome card: one on Bikfaya's Rue des Cèdres (a
// building with an alias, to show one), else on the town's street with the most buildings.
async function findExample() {
  const c = store.communes.find(x => x.fr === "Bikfaya") ?? store.communes.reduce((a, b) => (b.addr > a.addr ? b : a));
  const data = await loadCommune(c.id);
  const s = data.streets.find(x => x.names[1] === "Rue des Cèdres" && x.addrs.length)
    ?? data.streets.reduce((a, b) => (b.addrs.length > a.addrs.length ? b : a), data.streets[0]);
  const a = s?.addrs.find(x => x.also.length) ?? s?.addrs[0];
  if (a) store.example = { num: a.num, s, c };
}

// ---------- start ----------
(async () => {
  const hashLang = (initialHash.match(/[&#]l=(ar|fr|en)/) ?? [])[1];
  setLang(hashLang ?? lang());
  applyTexts();
  await loadBase();
  // A published copy lists the base maps it offers (the tile services whose terms it accepted).
  if (store.site.bases) document.querySelectorAll("[name=base]").forEach(r => { r.parentElement.hidden = !store.site.bases.includes(r.value); });
  mv.drawBoundaries();
  show(welcome, true);
  await restoreHash();
  restored = true;
  mv.refresh();
  updateHash();
  await findExample();
  if (!selected && document.body.dataset.view === "home") show(welcome, true);
})();
