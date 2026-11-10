// Scores the viewer's own search on addresses drawn at random from the built map: each address is
// typed several ways (as written, sloppily, respelled, with a typing slip, under its alias) and the
// first result must be that building. Also checks where the viewer puts a number by its metres.
//
// Usage: node tools/geocode_eval.mjs [--n 1500] [--seed 1] [--failures 5]
// It runs viewer/js/search.js itself, reading viewer/data from disk; run the pipeline first.

import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const VIEWER = join(dirname(fileURLToPath(import.meta.url)), "..", "viewer");
const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? +process.argv[i + 1] : fallback;
};
const N = arg("n", 1500), SEED = arg("seed", 1), SHOW = arg("failures", 5);

// The viewer's modules expect a browser: give them files for fetch and nothing to remember.
globalThis.fetch = async url => {
  const file = join(VIEWER, url);
  return existsSync(file) ? { ok: true, json: async () => JSON.parse(readFileSync(file, "utf8")) } : { ok: false, status: 404 };
};
globalThis.localStorage = { getItem: () => null, setItem() {} };
globalThis.document = { documentElement: {} };

const { search, resolveAddress, spotOn } = await import("../viewer/js/search.js");
const { loadBase, loadCommune, store } = await import("../viewer/js/store.js");
const { haversine, norm, projectOnLine } = await import("../viewer/js/util.js");

let state = SEED >>> 0;
const random = () => {   // mulberry32
  state = (state + 0x6D2B79F5) >>> 0;
  let x = Math.imul(state ^ (state >>> 15), 1 | state);
  x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
  return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
};
const choice = list => list[Math.floor(random() * list.length)];

// Other ways the same Lebanese name is written in Latin letters.
const RESPELL = [[/ou/, "u"], [/ch/, "sh"], [/sh/, "ch"], [/ieh\b/, "iye"], [/eh\b/, "e"], [/([a-z])\1/, "$1"], [/y/, "i"],
  [/k/, "q"], [/q/, "k"], [/ei/, "ay"], [/aa/, "a"], [/([^aeiou ])e\b/, "$1eh"], [/ph/, "f"], [/kh/, "5"], [/\bain\b/, "3ain"]];
const TYPE = /^(rue|route|impasse|passage|avenue|boulevard|chemin|allee|ruelle|place|street|road|lane|de|des|du|la|le|el|al|\d+)$/;

// The words of a name that carry it (not "rue", "des" or numbers), longest first.
const keyWords = name => norm(name).split(" ").filter(w => !TYPE.test(w) && /^[a-z]+$/.test(w)).sort((a, b) => b.length - a.length);

function respell(name) {
  const text = norm(name);
  const options = RESPELL.filter(([re]) => keyWords(text).some(w => re.test(w)));
  if (!options.length) return null;
  const [re, to] = choice(options);
  const word = choice(keyWords(text).filter(w => re.test(w)));
  return text.replace(word, word.replace(re, to));
}

function slip(name) {
  const text = norm(name), word = keyWords(text).find(w => w.length >= 6);
  if (!word) return null;
  const i = 1 + Math.floor(random() * (word.length - 2)), kind = Math.floor(random() * 3);
  const typo = kind === 0 ? word.slice(0, i) + word[i + 1] + word[i] + word.slice(i + 2)        // two letters swapped
    : kind === 1 ? word.slice(0, i) + word.slice(i + 1)                                          // one dropped
      : word.slice(0, i) + choice([..."abcdefghijklmnopqrstuvwxyz"].filter(l => l !== word[i])) + word.slice(i + 1);
  return typo === word ? null : text.replace(word, typo);
}

await loadBase();
const weighted = store.communes.filter(c => c.addr > 0);
const total = weighted.reduce((sum, c) => sum + c.addr, 0);
const drawCommune = () => {
  let x = random() * total;
  for (const c of weighted) if ((x -= c.addr) < 0) return c;
  return weighted[weighted.length - 1];
};

const tests = {};
const record = (name, ok, query, got) => {
  const t = (tests[name] ??= { n: 0, ok: 0, failures: [] });
  t.n++;
  if (ok) t.ok++;
  else if (t.failures.length < SHOW) t.failures.push(`${query}  ->  ${got}`);
};

// The first result must be an address that resolves to the building `key`.
async function expectBuilding(name, query, key) {
  if (!query) return;
  const [first] = await search(query, 5);
  let got = first ? first.type : "nothing";
  if (first?.type === "address") {
    const res = await resolveAddress(first);
    got = res.address ? res.address.key : res.spot ? "a spot on the street" : "the street";
  }
  record(name, got === key, query, got);
}

const spotErrors = [];
for (let i = 0; i < N; i++) {
  const c = drawCommune();
  const data = await loadCommune(c.id);
  const a = choice(data.addr), s = data.streetById.get(a.sid);
  const [ar, fr, en] = s.names;
  await expectBuilding("as written, French", `${a.num} ${fr}, ${c.fr}`, a.key);
  await expectBuilding("as written, English", `${a.num} ${en}, ${c.en}`, a.key);
  await expectBuilding("as written, Arabic", `${ar}، رقم ${a.num}، ${c.ar}`, a.key);
  await expectBuilding("no accents or commas, number after the street", `${norm(fr)} ${a.num} ${norm(c.fr)}`, a.key);
  await expectBuilding("Arabic, number after the street", `${ar} ${a.num} ${c.ar}`, a.key);
  const bare = text => text.replace(/[أإآ]/g, "ا").replace(/ة/g, "ه").replace(/ى/g, "ي").replace(/[\u064B-\u0652]/g, "");
  await expectBuilding("Arabic typed without hamzas or ta marbuta", bare(`${ar} ${a.num} ${c.ar}`) !== `${ar} ${a.num} ${c.ar}` && bare(`${ar} ${a.num} ${c.ar}`), a.key);
  const town = respell(c.fr), street = respell(fr);
  await expectBuilding("town respelled", town && `${a.num} ${fr} ${town}`, a.key);
  await expectBuilding("street respelled", street && `${a.num} ${street} ${c.fr}`, a.key);
  const typo = slip(fr), townTypo = slip(c.fr);
  await expectBuilding("typing slip in the street", typo && `${a.num} ${typo} ${c.fr}`, a.key);
  await expectBuilding("typing slip in the town", townTypo && `${a.num} ${fr} ${townTypo}`, a.key);

  // The same building under one of its aliases, on another street.
  if (a.also.length) {
    const [sid, num] = choice(a.also);
    const row = store.streetNames.get(sid), ac = store.communes[row.c];
    await expectBuilding("alias, as written in French", `${num} ${row.names[1]}, ${ac.fr}`, a.key);
  }

  // A number is a distance: the spot the viewer gives a number must be where the building with
  // that number meets the street (buildings numbered by a driveway, or pushed up by a neighbour
  // closer than 2 m, are not at their number's metres and are left out).
  if (!a.access && s.addrs.filter(x => x.side === a.side && Math.abs(x.num - a.num) <= 4).length === 1) {
    const { spot } = spotOn(s, a.num);
    if (spot) {
      const onStreet = (lon, lat) => s.parts.map(p => projectOnLine(p, lon, lat)).reduce((x, y) => (y.dist < x.dist ? y : x)).point;
      const there = onStreet(spot.lon, spot.lat), foot = onStreet(a.lon, a.lat);   // along the street, not across it
      spotErrors.push(haversine(there[1], there[0], foot[1], foot[0]));
    }
  }
}

console.log(`${N} addresses drawn at random (seed ${SEED}); first result is the building:`);
for (const [name, t] of Object.entries(tests)) {
  console.log(`  ${name.padEnd(48)} ${(100 * t.ok / t.n).toFixed(1).padStart(5)}%  (${t.ok}/${t.n})`);
}
spotErrors.sort((x, y) => x - y);
const q = p => spotErrors[Math.min(spotErrors.length - 1, Math.floor(p * spotErrors.length))].toFixed(1);
console.log(`A number placed by its metres, against where its building meets the street (${spotErrors.length} buildings): ` +
  `median ${q(0.5)} m, 90% within ${q(0.9)} m, 99% within ${q(0.99)} m`);
if (SHOW) {
  for (const [name, t] of Object.entries(tests)) {
    if (t.failures.length) console.log(`\n${name}:\n  ${t.failures.join("\n  ")}`);
  }
}
