// Small shared helpers: text normalization, geometry, decoding of the compact data files.

// Harakat, and the combining madda and hamza that NFD splits أ إ آ ؤ ئ into: "الارز" typed without
// its hamza finds "الأرز".
const AR_DIACRITICS = /[\u064B-\u0655\u0640\u0670]/g;
const AR_LETTERS = { "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي" };
const AR_DIGITS = { "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9" };

// Lowercase, no accents or Arabic diacritics, unified Arabic letter forms, punctuation -> spaces.
export function norm(s) {
  return String(s ?? "")
    .toLowerCase()
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(AR_DIACRITICS, "")
    .replace(/[أإآٱةىؤئ]/g, c => AR_LETTERS[c])
    .replace(/[٠-٩]/g, c => AR_DIGITS[c])
    .replace(/œ/g, "oe")
    .replace(/[-'’`.,،;:()\/]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// A spelling-blind key for one normalized word, so that the ways a Lebanese name is written in
// Latin letters meet: "jounieh", "juniyah" and "jounie" are all "jn"; "achrafieh" and "ashrafiye"
// "ašrf". Consonants only (the first vowel kept as "a"), with the French and English digraphs for
// one sound merged and Arabizi digits read as letters. Arabic words lose their article and long
// vowels. Used only when a search finds nothing as typed.
export function skeleton(word) {
  let s = word;
  if (/^\d+$/.test(s)) return s;
  if (/[\u0600-\u06FF]/.test(s)) {
    s = s.replace(/^ال(?=..)/, "");
    return s[0] + s.slice(1).replace(/[اوي]/g, "").replace(/(.)\1+/g, "$1");
  }
  if (/[a-z]/.test(s) && /\d/.test(s)) s = s.replace(/[32]/g, "a").replace(/7/g, "h").replace(/5/g, "kh").replace(/8/g, "gh").replace(/9/g, "s");
  s = s.replace(/sch|tch|ch|sh/g, "š").replace(/ph/g, "f").replace(/kh|ck|qu|q/g, "k").replace(/gh/g, "g")
    .replace(/th/g, "t").replace(/dh/g, "d").replace(/x/g, "ks").replace(/c(?=[eiy])/g, "s").replace(/c/g, "k")
    .replace(/w/g, "u").replace(/y/g, "i");
  const head = /[aeiou]/.test(s[0]) ? "a" : s[0];
  return (head + s.slice(1).replace(/[aeiouh]/g, "")).replace(/(.)\1+/g, "$1");
}

// Edit distance counting a swap of two neighbouring letters as one edit, cut off above `max`.
export function editDistance(a, b, max = 3) {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let prev2 = null, prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const row = [i];
    let low = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      let v = Math.min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) v = Math.min(v, prev2[j - 2] + 1);
      row.push(v);
      if (v < low) low = v;
    }
    if (low > max) return max + 1;
    prev2 = prev; prev = row;
  }
  return prev[b.length];
}

export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const R = 6371008.8;
const rad = d => d * Math.PI / 180;

export function haversine(lat1, lon1, lat2, lon2) {
  const a = Math.sin(rad(lat2 - lat1) / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lon2 - lon1) / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

// Compass bearing in degrees (0 = north, clockwise) from point 1 to point 2.
export function bearing(lat1, lon1, lat2, lon2) {
  const y = Math.sin(rad(lon2 - lon1)) * Math.cos(rad(lat2));
  const x = Math.cos(rad(lat1)) * Math.sin(rad(lat2)) - Math.sin(rad(lat1)) * Math.cos(rad(lat2)) * Math.cos(rad(lon2 - lon1));
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

// Local equirectangular projection in metres around a reference latitude (fine at street scale).
export function localXY(lat0) {
  const kx = Math.cos(rad(lat0)) * R * Math.PI / 180, ky = R * Math.PI / 180;
  return (lon, lat) => [lon * kx, lat * ky];
}

// Nearest point on a polyline [[lon, lat], ...]: {dist, along, index, t, point:[lon,lat], length}.
export function projectOnLine(coords, lon, lat) {
  const xy = localXY(lat);
  const [px, py] = xy(lon, lat);
  let best = { dist: Infinity }, along = 0;
  for (let i = 1; i < coords.length; i++) {
    const [ax, ay] = xy(...coords[i - 1]), [bx, by] = xy(...coords[i]);
    const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy, seg = Math.sqrt(len2);
    const t = len2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0;
    const qx = ax + t * dx, qy = ay + t * dy, d = Math.hypot(px - qx, py - qy);
    if (d < best.dist) {
      const [lo0, la0] = coords[i - 1], [lo1, la1] = coords[i];
      best = { dist: d, along: along + t * seg, index: i, t, point: [lo0 + t * (lo1 - lo0), la0 + t * (la1 - la0)] };
    }
    along += seg;
  }
  best.length = along;
  return best;
}

// Join a street's segments (cut at every junction) into continuous lines, so a name can run
// along several blocks instead of being squeezed into one.
export function chainParts(parts) {
  const key = p => `${p[0]},${p[1]}`;
  const ends = new Map();
  parts.forEach((p, i) => {
    for (const [end, pt] of [[0, p[0]], [1, p[p.length - 1]]]) {
      const k = key(pt);
      if (!ends.has(k)) ends.set(k, []);
      ends.get(k).push([i, end]);
    }
  });
  const used = new Uint8Array(parts.length), lines = [];
  const walk = (i, end) => {
    let line = end === 0 ? parts[i].slice() : parts[i].slice().reverse();
    used[i] = 1;
    for (;;) {
      const list = ends.get(key(line[line.length - 1]));
      const next = list?.length === 2 ? list.find(([j]) => !used[j]) : null;
      if (!next) break;
      used[next[0]] = 1;
      const seg = next[1] === 0 ? parts[next[0]] : parts[next[0]].slice().reverse();
      line = line.concat(seg.slice(1));
    }
    return line;
  };
  parts.forEach((p, i) => {
    for (const end of [0, 1]) {
      if (!used[i] && ends.get(key(end ? p[p.length - 1] : p[0])).length !== 2) lines.push(walk(i, end));
    }
  });
  parts.forEach((_, i) => { if (!used[i]) lines.push(walk(i, 0)); });   // closed loops
  return lines;
}

// The point `metres` along a polyline [[lon, lat], ...] measured as `total` metres long, moved
// `offset` metres to its left (negative: right): {lon, lat}, or null past either end.
export function pointAlong(coords, metres, total, offset = 0) {
  const xy = localXY(coords[0][1]);
  const pts = coords.map(([lon, lat]) => xy(lon, lat));
  let length = 0;
  for (let i = 1; i < pts.length; i++) length += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
  let left = metres * length / (total || length);
  if (!(length > 0) || left < 0 || left > length + 1) return null;
  for (let i = 1; i < pts.length; i++) {
    const dx = pts[i][0] - pts[i - 1][0], dy = pts[i][1] - pts[i - 1][1], seg = Math.hypot(dx, dy);
    if (left <= seg || i === pts.length - 1) {
      const t = seg ? Math.min(1, left / seg) : 0;
      const x = pts[i - 1][0] + t * dx - (seg ? dy / seg * offset : 0), y = pts[i - 1][1] + t * dy + (seg ? dx / seg * offset : 0);
      const [kx, ky] = xy(1, 1);
      return { lon: x / kx, lat: y / ky };
    }
    left -= seg;
  }
  return null;
}

// Rings stored as [x0, y0, dx1, dy1, ...] integers -> [[lat, lng], ...] for Leaflet.
export function decodeRing(flat, scale) {
  const out = new Array(flat.length / 2);
  let x = 0, y = 0;
  for (let i = 0; i < flat.length; i += 2) {
    x += flat[i]; y += flat[i + 1];
    out[i / 2] = [y / scale, x / scale];
  }
  return out;
}

export const decodePolys = (p, scale = 1e5) => p.map(rings => rings.map(r => decodeRing(r, scale)));

// Point-in-polygon on decoded [[lat, lng], ...] rings (even-odd rule, holes included).
export function inPolys(polys, lat, lng) {
  for (const rings of polys) {
    let inside = false;
    for (const ring of rings) {
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const [yi, xi] = ring[i], [yj, xj] = ring[j];
        if ((yi > lat) !== (yj > lat) && lng < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside;
      }
    }
    if (inside) return true;
  }
  return false;
}

export function debounce(fn, ms) {
  let id;
  return (...a) => { clearTimeout(id); id = setTimeout(() => fn(...a), ms); };
}

export async function fetchJSON(url) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

export async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch { return false; }
}
