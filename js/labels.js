// DOM label layer with greedy collision detection.
// Labels are plain HTML so Arabic shapes and renders correctly; the highest-priority label wins
// a spot and anything overlapping it is skipped. Recomputed after every move or zoom.

const ctx = document.createElement("canvas").getContext("2d");
const widths = new Map();

export function textWidth(text, font) {
  const key = font + "|" + text;
  let w = widths.get(key);
  if (w === undefined) {
    ctx.font = font;
    w = ctx.measureText(text).width;
    widths.set(key, w);
  }
  return w;
}

const CELL = 64;

export const LabelOverlay = L.Layer.extend({
  // provider(zoom, bounds) -> [{lat, lng, text, cls, font, prio, angle?, key?, minSep?, pad?, onClick?}]
  initialize(provider) {
    this._provider = provider;
    this._current = [];
  },

  onAdd(map) {
    this._el = L.DomUtil.create("div", "label-layer", map.getPane("labelPane"));
    L.DomEvent.on(this._el, "click", this._onClick, this);
    L.DomEvent.disableClickPropagation(this._el);
    map.on("moveend", this.redraw, this);
    map.on("zoomstart", this._hide, this);
    this.redraw();
  },

  onRemove(map) {
    map.off("moveend", this.redraw, this);
    map.off("zoomstart", this._hide, this);
    this._el.remove();
  },

  _hide() { this._el.style.visibility = "hidden"; },

  _onClick(e) {
    const el = e.target.closest("[data-i]");
    const cand = el && this._current[+el.dataset.i];
    if (!cand?.onClick) return;
    // onClick may redraw the labels and detach e.target; Leaflet would then no longer see the
    // click as a label's and fire a map click too (opening the commune card), so stop it here.
    L.DomEvent.stop(e);
    cand.onClick(cand, e);
  },

  redraw() {
    const map = this._map;
    if (!map) return;
    const z = map.getZoom(), bounds = map.getBounds().pad(0.05);
    const cands = this._provider(z, bounds).sort((a, b) => b.prio - a.prio);
    const grid = new Map(), seen = new Map(), out = [];
    const size = map.getSize(), origin = map.containerPointToLayerPoint([0, 0]);
    const hit = (x0, y0, x1, y1) => {
      for (let gx = Math.floor(x0 / CELL); gx <= Math.floor(x1 / CELL); gx++) {
        for (let gy = Math.floor(y0 / CELL); gy <= Math.floor(y1 / CELL); gy++) {
          for (const b of grid.get(gx * 100003 + gy) ?? []) {
            if (x0 < b[2] && x1 > b[0] && y0 < b[3] && y1 > b[1]) return true;
          }
        }
      }
      return false;
    };
    const add = box => {
      for (let gx = Math.floor(box[0] / CELL); gx <= Math.floor(box[2] / CELL); gx++) {
        for (let gy = Math.floor(box[1] / CELL); gy <= Math.floor(box[3] / CELL); gy++) {
          const k = gx * 100003 + gy;
          if (!grid.has(k)) grid.set(k, []);
          grid.get(k).push(box);
        }
      }
    };
    for (const c of cands) {
      const p = map.latLngToLayerPoint([c.lat, c.lng]);
      const cx = p.x - origin.x, cy = p.y - origin.y;
      if (cx < -50 || cy < -50 || cx > size.x + 50 || cy > size.y + 50) continue;
      const pad = c.pad ?? 3;
      const w = textWidth(c.text, c.font) + 2 * pad, h = (parseFloat(c.font.match(/(\d+(?:\.\d+)?)px/)[1]) * 1.25) + 2 * pad;
      const a = (c.angle ?? 0) * Math.PI / 180;
      const hw = (Math.abs(Math.cos(a)) * w + Math.abs(Math.sin(a)) * h) / 2;
      const hh = (Math.abs(Math.sin(a)) * w + Math.abs(Math.cos(a)) * h) / 2;
      const box = [cx - hw, cy - hh, cx + hw, cy + hh];
      if (hit(...box)) continue;
      if (c.key !== undefined && c.minSep) {
        const prev = seen.get(c.key) ?? [];
        if (prev.some(([x, y]) => Math.hypot(x - cx, y - cy) < c.minSep)) continue;
        prev.push([cx, cy]);
        seen.set(c.key, prev);
      }
      add(box);
      out.push([c, p]);
    }
    this._current = out.map(([c]) => c);
    const html = out.map(([c, p], i) =>
      `<span class="lbl ${c.cls}${c.onClick ? " clickable" : ""}" data-i="${i}" ` +
      `style="transform:translate(${p.x.toFixed(1)}px,${p.y.toFixed(1)}px) rotate(${(c.angle ?? 0).toFixed(1)}deg) translate(-50%,-50%)">` +
      `${c.html ?? escapeText(c.text)}</span>`).join("");
    this._el.innerHTML = html;
    this._el.style.visibility = "";
  },
});

function escapeText(s) {
  return String(s).replace(/[&<>]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch]));
}
