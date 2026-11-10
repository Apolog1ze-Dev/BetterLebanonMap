// One search box for communes, places, streets and full addresses, in any of the three languages.
// "22 rue des cedres bikfaya", "شارع الأرز 22 بكفيا" and "bikfaya" all work; accents optional.
// When nothing matches as typed, the query is read again by sound and with one slip allowed per
// word ("22 rue des cedrse bikfaiya"), see skeleton() in util.js.

import { langIndex, pick } from "./i18n.js";
import { communeAt, loadCommune, loadPois, loadSearch, spineOf, store } from "./store.js";
import { editDistance, norm, pointAlong, skeleton } from "./util.js";

const TYPE_WORDS = new Set(["rue", "route", "impasse", "passage", "avenue", "boulevard", "ruelle", "street", "road", "lane",
  "st", "rd", "شارع", "طريق", "زاروب", "ممر", "جاده", "اوتوستراد"]);
// Words that only announce a house number ("رقم 22", "no 22").
const NUMBER_WORDS = new Set(["رقم", "no", "n", "n°", "nº", "numero", "number", "num"]);
// Words too common to tell streets apart when read by sound.
const SMALL_WORDS = new Set(["el", "al", "de", "du", "des", "la", "le", "les", "l", "d", "of", "the", "ed", "er", "es", "ech", "en"]);
const SRC_BONUS = [6, 4, 4, 0, 2, 0, 4];
const FUZZY_PENALTY = 15;
const isNumber = t => /^\d+$/.test(t);
let index = null;

const wordsOf = text => {
  const out = new Set();
  for (const w of text.split(" ")) {
    if (!w) continue;
    out.add(w);
    if (w.startsWith("ال") && w.length > 3) out.add(w.slice(2));   // Arabic article
  }
  return [...out];
};

// A name read by sound: its words' skeletons, small words left out.
const soundOf = text => {
  const words = text.split(" ").filter(Boolean);
  const kept = words.filter(w => !SMALL_WORDS.has(w));
  return (kept.length ? kept : words).map(skeleton).join(" ");
};
// The same sound, or one consonant apart in a word of four or more.
const soundsLike = (a, b) => a === b || (a.length >= 3 && b.length >= 3 && a.length + b.length >= 7 && editDistance(a, b, 1) <= 1);
// One typing slip apart, as spelled (short words are too easily another word).
const slipOf = (a, b) => a.length >= 5 && b.length >= 5 && editDistance(a, b, 1) <= 1;

async function prepare() {
  if (index) return index;
  await Promise.all([loadSearch(), loadPois()]);
  const streets = store.search.map(r => {
    const keys = r.names.map(norm);
    return { ...r, keys, words: wordsOf(keys.join(" ")) };
  });
  const byPrefix = new Map();
  streets.forEach((s, i) => {
    for (const w of s.words) {
      const k = w.slice(0, 2);
      if (!byPrefix.has(k)) byPrefix.set(k, []);
      const list = byPrefix.get(k);
      if (list[list.length - 1] !== i) list.push(i);
    }
  });
  const named = list => list.map(x => {
    const keys = x.names.filter(Boolean).map(norm);
    return { x, keys, words: wordsOf(keys.join(" ")) };
  });
  // Districts and governorates as location words: "Gouvernorat de Beyrouth" -> "beyrouth".
  const AREA_WORDS = /^(gouvernorat|governorate|district|caza|محافظه|قضاء|de|du|des|la|l|d)$/;
  const areaKeys = a => [a.ar, a.fr, a.en].map(n => norm(n).split(" ").filter(w => !AREA_WORDS.test(w)).join(" ")).filter(Boolean);
  const areas = [
    ...store.districts.map((d, i) => ({ keys: areaKeys(d), test: c => c.d === i })),
    ...store.governorates.map((g, i) => ({ keys: areaKeys(g), test: c => c.g === i })),
  ];
  index = {
    streets, byPrefix, areas,
    communes: named(store.communes.map(c => ({ c, names: [c.ar, c.fr, c.en] }))),
    places: named(store.places.map(p => ({ p, names: p.names }))),
    pois: named(store.pois.map(p => ({ p, names: p.names }))),
  };
  return index;
}

export const warmUp = () => prepare();

const matchesAll = (tokens, words) => tokens.every(t => words.some(w => w.startsWith(t)));

// The communes named in the query as whole words, longest name first: [{c, k: the name as found}].
// Several may be: "Route de Baaourta, Naameh" is a road of Naameh named after the next town.
function findCommunes(q, idx) {
  const padded = ` ${q} `, found = new Map();
  for (const e of idx.communes) {
    for (const k of e.keys) {
      if (k.length >= 3 && padded.includes(` ${k} `) && !(found.get(e.x.c)?.k.length >= k.length)) found.set(e.x.c, { c: e.x.c, k });
    }
  }
  return [...found.values()].sort((x, y) => y.k.length - x.k.length).slice(0, 6);
}

// The communes a run of one to five words of the query sounds like, or is one typing slip from:
// [{c, rest: the query without those words, dist, last: the run ends the query}], best first --
// the end of the query, where a town is usually written, then the longest run, the nearest spelling.
function soundsLikeCommunes(tokens, idx) {
  idx.communeSounds ??= idx.communes.flatMap(e => e.keys.map(k => ({ c: e.x.c, k, sound: soundOf(k) })));
  const found = new Map();
  for (let n = Math.min(5, tokens.length - 1); n >= 1; n--) {
    for (let i = 0; i + n <= tokens.length; i++) {
      const span = tokens.slice(i, i + n);
      if (span.some(t => isNumber(t) || TYPE_WORDS.has(t) || NUMBER_WORDS.has(t))) continue;
      const text = span.join(" "), sound = soundOf(text);
      const where = i + n === tokens.length ? 0 : i === 0 ? 1 : 2;
      for (const e of idx.communeSounds) {
        if (!soundsLike(sound, e.sound) && !slipOf(text, e.k)) continue;
        const cand = { c: e.c, where, n, dist: editDistance(text, e.k, 8) + (sound === e.sound ? 0 : 2), last: where === 0,
          rest: [...tokens.slice(0, i), ...tokens.slice(i + n)].join(" ") };
        const old = found.get(e.c);
        if (!old || rank(cand, old) < 0) found.set(e.c, cand);
      }
    }
  }
  return [...found.values()].sort(rank).slice(0, 6);
}
const rank = (x, y) => x.where - y.where || y.n - x.n || x.dist - y.dist || y.c.addr - x.c.addr;

// Streets by the sound of their words: skeleton -> streets, and the skeletons one letter apart.
function soundIndex(idx) {
  if (idx.sounds) return idx.sounds;
  const bySound = new Map(), ofWord = new Map(), near = new Map(), nearWord = new Map();
  const file = (map, key, value) => (map.get(key) ?? map.set(key, []).get(key)).push(value);
  idx.streets.forEach((s, i) => {
    for (const w of s.words) {
      let k = ofWord.get(w);
      if (k === undefined) ofWord.set(w, k = skeleton(w));
      let list = bySound.get(k);
      if (!list) bySound.set(k, list = []);
      if (list[list.length - 1] !== i) list.push(i);
    }
  });
  for (const k of bySound.keys()) if (k.length >= 3 && !isNumber(k)) for (const d of shortened(k)) file(near, d, k);
  for (const w of ofWord.keys()) if (w.length >= 5 && !isNumber(w)) for (const d of shortened(w)) file(nearWord, d, w);
  return (idx.sounds = { bySound, ofWord, near, nearWord });
}

const shortened = k => {
  const out = new Set([k]);
  for (let i = 0; i < k.length; i++) out.add(k.slice(0, i) + k.slice(i + 1));
  return out;
};

// Streets whose words sound like every token, or are one typing slip from it: [{st, dist: how far
// the spelling is from the street's own}].
function findBySound(required, reading, idx) {
  const sounds = soundIndex(idx);
  const tokens = required.filter(t => !SMALL_WORDS.has(t));
  const lists = (tokens.length ? tokens : required).map(t => {
    const k = isNumber(t) ? t : skeleton(t);
    const alike = new Set(sounds.bySound.has(k) ? [k] : []);
    if (!isNumber(t)) {
      if (k.length >= 3) for (const d of shortened(k)) for (const other of sounds.near.get(d) ?? []) if (soundsLike(k, other)) alike.add(other);
      if (t.length >= 5) for (const d of shortened(t)) for (const w of sounds.nearWord.get(d) ?? []) if (slipOf(t, w)) alike.add(sounds.ofWord.get(w));
    }
    const streets = new Set();
    for (const a of alike) for (const i of sounds.bySound.get(a)) streets.add(i);
    return { t, alike, streets };
  }).sort((a, b) => a.streets.size - b.streets.size);
  const out = [];
  for (const i of lists[0].streets) {
    const st = idx.streets[i];
    if (reading.commune && st.c !== reading.commune.idx) continue;
    if (reading.area && !reading.area(store.communes[st.c])) continue;
    if (!lists.every(l => l.streets.has(i))) continue;
    let dist = 0;
    for (const l of lists) {
      let best = 8;
      for (const w of st.words) if (l.alike.has(sounds.ofWord.get(w))) best = Math.min(best, editDistance(l.t, w, 8));
      dist += best;
    }
    out.push({ st, dist });
  }
  return out;
}

function findAsTyped(required, reading, idx) {
  const seed = required.reduce((x, y) => (y.length > x.length ? y : x));
  const pool = seed.length >= 2 ? idx.byPrefix.get(seed.slice(0, 2)) ?? [] : idx.streets.map((_, i) => i);
  const out = [];
  for (const i of pool) {
    const st = idx.streets[i];
    if (reading.commune && st.c !== reading.commune.idx) continue;
    if (reading.area && !reading.area(store.communes[st.c])) continue;
    if (matchesAll(required, st.words)) out.push({ st, dist: 0 });
  }
  return out;
}

// One pass over the query. bySound: read names by their sound where they are not found as typed.
function pass(q, idx, bySound) {
  const results = [];
  const qTokens = q.split(" ");
  const penalty = bySound ? FUZZY_PENALTY : 0;

  // Communes and places by name.
  if (bySound) {
    const sound = soundOf(q);
    for (const [list, type, base] of [[idx.communes, "commune", 60], [idx.places, "place", 30]]) {
      for (const e of list) {
        const k = e.keys.find(key => soundsLike(sound, soundOf(key)));
        if (!k) continue;
        const score = base + 20 - penalty - 2 * editDistance(q, k, 8);
        results.push(type === "commune" ? { type, c: e.x.c, score: score - e.x.c.kind * 3 } : { type, p: e.x.p, score });
      }
    }
  } else {
    for (const e of idx.communes) {
      if (!matchesAll(qTokens, e.words)) continue;
      const exact = e.keys.includes(q) ? 40 : e.keys.some(k => k.startsWith(q)) ? 25 : 10;
      results.push({ type: "commune", c: e.x.c, score: 60 + exact - e.x.c.kind * 3 });
    }
    for (const e of idx.places) {
      if (!matchesAll(qTokens, e.words)) continue;
      results.push({ type: "place", p: e.x.p, score: 30 + (e.keys.includes(q) ? 20 : 0) });
    }
  }

  // Streets and addresses, read two ways: with a commune named in the query ("rue des cedres
  // bikfaya") and as plain street text ("rue hamra", where Hamra is also a village).
  const hasType = qTokens.some(t => TYPE_WORDS.has(t));
  const readings = [{ text: q, commune: null }];
  for (const { c, k } of findCommunes(q, idx)) {
    // Written last, the town is those last words: "Route de Qaa Ouadi El-Khanzir, Qaa" is a road of Qaa.
    const last = q.endsWith(` ${k}`);
    readings.push({ text: last ? q.slice(0, -k.length).trim() : ` ${q} `.replace(` ${k} `, " ").trim(), commune: c, last });
  }
  if (bySound) {
    for (const heard of soundsLikeCommunes(qTokens, idx)) {
      if (!readings.some(r => r.commune === heard.c)) readings.push({ text: heard.rest, commune: heard.c, last: heard.last, off: heard.dist });
    }
  }
  // A district or governorate name narrows the search ("rue hamra beyrouth", "route des cedres metn").
  for (const area of idx.areas) {
    const k = area.keys.find(key => key.length >= 3 && ` ${q} `.includes(` ${key} `));
    if (k) readings.unshift({ text: ` ${q} `.replace(` ${k} `, " ").trim(), area: area.test });
  }
  for (const reading of readings) {
    let tokens = reading.text.split(" ").filter(Boolean);
    // Named places: every word of the reading in the place's name, in the commune or area named.
    if (!bySound && tokens.length) {
      for (const e of idx.pois) {
        if (!matchesAll(tokens, e.words)) continue;
        if (reading.commune || reading.area) {
          e.c ??= communeAt(e.x.p.lat, e.x.p.lon)?.idx ?? -1;
          if (reading.commune ? e.c !== reading.commune.idx : !(e.c >= 0 && reading.area(store.communes[e.c]))) continue;
        }
        const whole = e.keys.includes(reading.text) ? 18 : e.keys.some(k => k.startsWith(reading.text)) ? 8 : 0;
        results.push({ type: "poi", p: e.x.p, score: 28 + whole + (reading.commune ? 30 : reading.area ? 20 : 0) });
      }
    }
    tokens = tokens.filter((t, i) => !(NUMBER_WORDS.has(t) && (isNumber(tokens[i + 1] ?? "") || isNumber(tokens[i - 1] ?? ""))));
    let number = null;
    if (tokens.length > 1 && isNumber(tokens[0])) number = +tokens.shift();
    let required = tokens.filter(t => !TYPE_WORDS.has(t));
    if (!required.length) {
      if (reading.commune && number === null) {
        results.push({ type: "commune", c: reading.commune, score: (hasType ? 60 : 120) - penalty - 2 * (reading.off ?? 0) });
      }
      continue;
    }
    const scoreOf = (st, phrase) => {
      const size = Math.log10((store.communes[st.c]?.addr ?? 0) + 10);   // bigger towns first on ties
      let score = 40 + SRC_BONUS[st.src] - Math.min(10, st.keys[1].length / 8) + size * 2 + (hasType ? 20 : 0);
      if (st.keys.includes(phrase)) score += 25;
      else if (st.keys.some(k => k.includes(phrase))) score += 12;
      if (reading.commune) score += 30 + (reading.last ? 6 : 0) - 2 * (reading.off ?? 0);   // a town is written last
      if (reading.area) score += 20;
      return score;
    };
    // As typed first: with a town heard by sound, the street itself may be spelled right.
    const find = req => {
      const typed = findAsTyped(req, reading, idx);
      return typed.length || !bySound ? typed : findBySound(req, reading, idx);
    };
    const emit = (tokens, required, number) => {
      const phrase = tokens.join(" ");
      const hits = find(required).map(({ st, dist }) => ({ s: st, score: scoreOf(st, phrase) - penalty - 4 * dist }))
        .sort((x, y) => y.score - x.score).slice(0, 40);
      for (const h of hits) {
        if (number !== null) results.push({ type: "address", s: h.s, number, score: h.score + 15 });
        results.push({ type: "street", s: h.s, score: h.score });
      }
      return hits.some(h => h.s.keys.includes(phrase));
    };
    const named = emit(tokens, required, number);
    // A number after the street is a house number ("rue des cedres 12") unless the words with it
    // are a street's whole name ("Impasse des Cèdres 360").
    const at = tokens.findLastIndex(isNumber);
    if (number === null && at > 0 && !named && required.length > 1) {
      const rest = tokens.filter((_, i) => i !== at);
      emit(rest, rest.filter(t => !TYPE_WORDS.has(t)), +tokens[at]);
    }
  }
  if (hasType) for (const r of results) if (r.type !== "street" && r.type !== "address") r.score -= 40;
  return results;
}

export async function search(query, limit = 10) {
  const idx = await prepare();
  const q = norm(query).replace(/#(?=\d)/g, "");
  if (!q) return [];
  let results = pass(q, idx, false);
  // Nothing as typed, or an address (a number or a street word) that no street answers: by sound.
  const street = results.some(r => r.type === "street" || r.type === "address");
  const tokens = q.split(" ");
  if (!results.length || (!street && tokens.length > 1 && tokens.some(t => isNumber(t) || TYPE_WORDS.has(t)))) {
    results = results.concat(pass(q, idx, true));
  }

  const seen = new Set();
  return results.sort((a, b) => b.score - a.score).filter(r => {
    const key = r.type + (r.c?.id ?? r.s?.sid ?? `${r.p?.lon},${r.p?.lat}`) + (r.number ?? "");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, limit);
}

// A place's name in the current language, else in any it has.
export const placeName = p => p.names[langIndex()] ?? p.names.find(Boolean) ?? "";

// Display texts for a result row: [main, secondary].
export function describe(r) {
  if (r.type === "commune") {
    const d = store.districts[r.c.d];
    return [pick([r.c.ar, r.c.fr, r.c.en]), d ? pick([d.ar, d.fr, d.en]) : ""];
  }
  if (r.type === "place" || r.type === "poi") {
    const c = communeAt(r.p.lat, r.p.lon);
    return [placeName(r.p), c ? pick([c.ar, c.fr, c.en]) : ""];
  }
  const c = store.communes[r.s.c];
  const where = pick([c.ar, c.fr, c.en]);
  if (r.type === "street") return [pick(r.s.names), where];
  return [`${r.number} ${pick(r.s.names)}`, where];
}

// Where an address result is. The building with that number on the street: {address, exact}, with
// `as` (the street and number it was found under) when the number is an alias of a building
// whose own address is on another street. For a number no building has, the spot that many
// metres along the street, see spotOn.
export async function resolveAddress(r) {
  const c = store.communes[r.s.c];
  const data = await loadCommune(c.id);
  const street = data.streetById.get(r.s.sid);
  if (!street) return { street: null };
  const own = street.addrs.find(a => a.num === r.number);
  if (own) return { street, address: own, exact: true };
  const alias = street.alts.find(a => a.num === r.number);
  if (alias) {
    const address = (await loadCommune(alias.home)).addrByKey.get(alias.key);
    if (address) return { street, address, exact: true, as: { s: street, num: alias.num } };
  }
  return { street, ...spotOn(street, r.number) };
}

// A number is a distance, so one that no building has still has a place: {spot: {lat, lon, num,
// side}} that many metres from the street's start, 6 m off its line on the number's side, with
// `nearest`, the closest number a building has on that side; {beyond} past the street's end.
export function spotOn(street, number) {
  const numbered = [...street.addrs, ...street.alts];
  const sameSide = numbered.filter(a => a.num % 2 === number % 2);
  const pool = sameSide.length ? sameSide : numbered;
  const nearest = pool.length ? pool.reduce((a, b) => (Math.abs(b.num - number) < Math.abs(a.num - number) ? b : a)).num : null;
  const p = number <= street.len + 2 ? pointAlong(spineOf(street), Math.min(number, street.len), street.len, number % 2 ? 6 : -6) : null;
  return p ? { spot: { ...p, num: number, side: number % 2 ? 0 : 1 }, nearest } : { beyond: true, nearest };
}
