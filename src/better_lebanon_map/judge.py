"""Judge which street a house is reached from, with a vision-language model running on this machine.

A house takes its nearest street, or the street a driveway leads to when one is drawn or seen in
satellite imagery (access.py). The judge goes house by house, from the farthest from any street to
the nearest, and asks a local vision-language model which of up to four candidate streets the house
is reached from. The model sees one picture of two panels at the same scale, north up: the satellite
photo and a map drawn from OSM's streets and buildings, the house outlined in red and the candidate
streets lettered A-D in colour. It answers a letter (or "none") with a confidence, twice, the
letters shuffled the second time. An answer both passes give with confidence AUTO or more is
applied at the next build; any other waits in the approval queue (viewer/judge.html, served by
`serve`), least confident first. A house with a single street within SEARCH_M needs no judging.

The model is any vision model behind an OpenAI-compatible endpoint: Ollama (the default,
`ollama pull qwen2.5vl:7b`), llama.cpp's llama-server, vLLM or LM Studio. `--backend nearest`
answers without a model (the nearest street), to try the queue. Progress is kept in
data/judge/judge.sqlite: stop with Ctrl-C at any time and run again to resume.

Usage:
  uv run python -I -m better_lebanon_map.judge run [--model qwen2.5vl:7b] [--endpoint http://localhost:11434/v1]
                                                   [--limit N] [--min-distance M]
  uv run python -I -m better_lebanon_map.judge stats
  uv run python -I -m better_lebanon_map.judge plan    # re-plan after a new pipeline run
  uv run python -I -m better_lebanon_map.judge pilot --model ...   # score a model on the houses in PILOT first
  --method driveway: the model points at where the way in meets a street (one satellite picture,
  two zooms) instead of choosing a lettered street; the street is the candidate nearest that spot.
The satellite tiles are Esri World Imagery by default (`--imagery` for another tile URL); check the
provider's terms before judging many houses.
"""

import argparse
import base64
import io
import json
import math
import os
import re
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from PIL import Image, ImageDraw, ImageFont, ImageStat
from pyproj import Transformer
from shapely.ops import nearest_points

from . import addressing
from .localities import METRIC_CRS

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data/judge/judge.sqlite"
TILES = ROOT / "data/judge/tiles"
PILOT = ROOT / "data/judge/pilot.tsv"   # houses a person read off the same pictures, to score a model
IMAGERY = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
SEARCH_M = 250.0       # candidate streets this close to the house
MAX_CANDIDATES = 4
AUTO = 80              # both passes agree at least this confident: applied without review
PANEL = 512
LETTERS = "ABCD"
COLORS = [(30, 144, 255), (255, 140, 0), (186, 85, 211), (46, 204, 113)]
COLOR_NAMES = ["blue", "orange", "purple", "green"]
WORLD = 40075016.686   # metres around the Web Mercator world
TO_MERC = Transformer.from_crs(METRIC_CRS, 3857, always_xy=True)
TO_WGS = Transformer.from_crs(METRIC_CRS, 4326, always_xy=True)
FROM_MERC = Transformer.from_crs(3857, METRIC_CRS, always_xy=True)
POINT_PX = 1000        # the driveway picture: its pixels and the 0-1000 grid some models answer in agree
SNAP_M = 20.0          # a spot pointed at this close to a candidate street names that street

SCHEMA = """
CREATE TABLE IF NOT EXISTS plan (key TEXT PRIMARY KEY, rank INTEGER, distance REAL);
CREATE TABLE IF NOT EXISTS judgments (
  key TEXT PRIMARY KEY,
  status TEXT,       -- auto | queue | single | approved | corrected | rejected | skipped | error
  distance REAL,     -- metres to the nearest street
  context TEXT,      -- JSON: house ring, candidates (names, distance, junction, lines), lon/lat
  choice TEXT,       -- the street it is reached from: a candidate letter, or "none"
  confidence REAL, reason TEXT, answers TEXT, model TEXT, decided_by TEXT, updated TEXT);
CREATE INDEX IF NOT EXISTS judgments_status ON judgments(status, confidence);
"""

PROMPT = """You check road access for a house in Lebanon. The picture has two panels of the same area at \
the same scale, north up: on the left a satellite photo, on the right a street map. The house is \
outlined in red in both. Candidate streets are drawn in colour and lettered: {legend}.
From which candidate street is this house reached, by car or on foot: through a driveway, track, \
path, stairs or gate that you can see in the photo? Do not simply pick the nearest street; look for \
the way in. If no way in from any candidate can be seen, answer "none".
Reply with JSON only: {{"access": "<letter or none>", "confidence": <0-100>, "reason": "<one short sentence>"}}"""

# The other method (--method driveway): the model points at where the way in meets a street, and the
# street is the candidate nearest that spot. Locating things is what these models are trained for;
# choosing among lettered options is not.
DRIVEWAY_PROMPT = """Satellite photo, north up, {size} by {size} pixels. The building outlined in red is a house; \
the yellow lines are mapped streets. Which street is this house reached from, through a driveway, yard, track, \
path or stairs that you can see? Point to the place on that street where the way in joins it, not to the house. \
Reply with JSON only: {{"point_2d": [x, y]}}, or {{"seen": "none"}} if no way in can be seen."""


def connect(path=DB):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Area:
    """The latest build's streets, ways and buildings (data/interim), in metres."""

    def __init__(self, root=ROOT):
        stage = root / "data/interim/stage"
        self.streets = gpd.read_parquet(stage / "streets.parquet",
                                        columns=["street_id", "name_ar", "name_fr", "name_en", "geometry"]).set_index("street_id")
        edges = gpd.read_parquet(stage / "edges.parquet", columns=["street_id", "geometry"])
        self.ways = edges.geometry.values                                  # every way, for the map panel
        self.edges = edges[edges.street_id >= 0].reset_index(drop=True)   # streets a house can take
        self.etree, self.wtree = shapely.STRtree(self.edges.geometry.values), shapely.STRtree(self.ways)
        b = addressing.addressable_buildings(gpd.read_parquet(root / "data/interim/buildings.parquet"))
        self.foot, self.point = b.geometry.values, b["point"].values
        self.keys = (b.osm_type.str[0] + b.osm_id.astype(str)).values
        self.index = {k: i for i, k in enumerate(self.keys)}
        self.btree = shapely.STRtree(self.foot)

    def candidates(self, i):
        """Up to MAX_CANDIDATES streets near house i, nearest first, none much farther than the nearest."""
        near = self.etree.query(self.foot[i], predicate="dwithin", distance=SEARCH_M)
        if not len(near):
            return []
        dist = shapely.distance(self.edges.geometry.values[near], self.foot[i])
        best = {}
        for e, d in zip(near, dist):
            sid = int(self.edges.street_id.values[e])
            if sid not in best or d < best[sid][0]:
                best[sid] = (float(d), e)
        ranked = sorted(best.items(), key=lambda kv: kv[1][0])
        reach = max(60.0, 2.5 * ranked[0][1][0])
        out = []
        for sid, (d, e) in ranked[:MAX_CANDIDATES]:
            if d > reach:
                break
            s = self.streets.loc[sid]
            out.append({"sid": sid, "dist": round(d, 1),
                        "junction": nearest_points(self.edges.geometry.values[e], self.foot[i])[0],
                        "name_fr": s.name_fr if isinstance(s.name_fr, str) else None,
                        "name_ar": s.name_ar if isinstance(s.name_ar, str) else None,
                        "name_en": s.name_en if isinstance(s.name_en, str) else None,
                        "geometry": s.geometry})
        return out

    def frame(self, i, cands):
        """A square around house i, in Web Mercator, showing every candidate's junction."""
        half = min(max(max(c["dist"] for c in cands) * 1.3 + 25, 45), 220)
        p = self.point[i]
        cx, cy = TO_MERC.transform(p.x, p.y)
        lat = TO_WGS.transform(p.x, p.y)[1]
        h = half / math.cos(math.radians(lat))
        return cx - h, cy - h, cx + h, cy + h

    def context(self, i, cands):
        """What the approval queue shows: the house, the candidates, in lon/lat."""
        lonlat = lambda g: np.round(np.column_stack(TO_WGS.transform(*shapely.get_coordinates(g).T)), 6).tolist()
        view = self.point[i].buffer(SEARCH_M + 100)
        return {"point": lonlat(self.point[i])[0], "house": lonlat(_outline(self.foot[i])),
                "candidates": [{"name_fr": c["name_fr"], "name_ar": c["name_ar"], "name_en": c["name_en"],
                                "dist": c["dist"], "junction": lonlat(c["junction"])[0],
                                "lines": [lonlat(part) for part in shapely.get_parts(c["geometry"].intersection(view))
                                          if part.geom_type == "LineString"]} for c in cands]}


# ---------- pictures ----------

def tile(z, x, y, url):
    f = TILES / str(z) / str(x) / f"{y}.jpg"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url.format(z=z, x=x, y=y), headers={"User-Agent": "BetterLebanonMap-judge/1.0"})
        for attempt in range(3):
            try:
                f.write_bytes(urllib.request.urlopen(req, timeout=30).read())
                break
            except OSError:
                time.sleep(1 + 2 * attempt)
        else:
            return None
    return Image.open(f).convert("RGB")


def satellite(frame, url, size=PANEL):
    """The satellite photo of a Web Mercator frame, `size` pixels square; a zoom level lower where the
    imagery has no tiles ("Map data not yet available")."""
    x0, y0, x1, y1 = frame
    z = min(19, max(1, math.ceil(math.log2(WORLD * size / (256 * (x1 - x0))))))
    while z >= 15:
        n = WORLD / 2 ** z
        tx = lambda x: (x + WORLD / 2) / n
        ty = lambda y: (WORLD / 2 - y) / n
        cols, rows = range(int(tx(x0)), int(tx(x1)) + 1), range(int(ty(y1)), int(ty(y0)) + 1)
        tiles = {(c, r): tile(z, c, r, url) for c in cols for r in rows}
        if all(t is not None and max(ImageStat.Stat(t).stddev) > 8 for t in tiles.values()):   # Esri's blank: 5.4
            mosaic = Image.new("RGB", (256 * len(cols), 256 * len(rows)))
            for (c, r), t in tiles.items():
                mosaic.paste(t, (256 * (c - cols[0]), 256 * (r - rows[0])))
            box = (256 * (tx(x0) - cols[0]), 256 * (ty(y1) - rows[0]), 256 * (tx(x1) - cols[0]), 256 * (ty(y0) - rows[0]))
            return mosaic.crop(tuple(round(v) for v in box)).resize((size, size), Image.LANCZOS)
        z -= 1
    return Image.new("RGB", (size, size), (90, 90, 90))


def _rings(geom):
    """Outer rings of a footprint's polygons (some footprints are multipolygons)."""
    return [shapely.get_exterior_ring(p) for p in shapely.get_parts(geom) if p.geom_type == "Polygon"]


def _outline(geom):
    """The outer ring of a footprint's largest polygon."""
    return max(_rings(geom), key=lambda r: shapely.area(shapely.Polygon(r)))


def _pixels(geom, frame, size=PANEL):
    x0, y0, x1, y1 = frame
    merc = np.column_stack(TO_MERC.transform(*shapely.get_coordinates(geom).T))
    return [((x - x0) / (x1 - x0) * size, (y1 - y) / (y1 - y0) * size) for x, y in merc]


def _font(size):
    for name in ("DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(area, i, cands, order, url):
    """The model's picture: satellite and map side by side, candidates lettered in `order`."""
    frame = area.frame(i, cands)
    sat, plan = satellite(frame, url), Image.new("RGB", (PANEL, PANEL), (242, 239, 233))
    m, s = ImageDraw.Draw(plan), ImageDraw.Draw(sat)
    x0, y0, x1, y1 = frame
    view = area.point[i].buffer((x1 - x0) * 0.8)
    for k in area.btree.query(view):
        for ring in _rings(area.foot[k]):
            m.polygon(_pixels(ring, frame), fill=(214, 208, 199), outline=(190, 182, 172))
    for k in area.wtree.query(view):
        for part in shapely.get_parts(area.ways[k]):
            m.line(_pixels(part, frame), fill=(160, 160, 160), width=9)
            m.line(_pixels(part, frame), fill=(255, 255, 255), width=7)
    font = _font(22)
    for slot, c in enumerate(order):
        color = COLORS[slot]
        for part in shapely.get_parts(c["geometry"].intersection(view)):
            if part.geom_type == "LineString":
                m.line(_pixels(part, frame), fill=color, width=7)
                s.line(_pixels(part, frame), fill=color, width=3)
        jx, jy = _pixels(c["junction"], frame)[0]
        for d in (m, s):
            d.ellipse((jx - 14, jy - 14, jx + 14, jy + 14), fill=color, outline=(255, 255, 255), width=2)
            d.text((jx, jy), LETTERS[slot], fill=(255, 255, 255), font=font, anchor="mm")
    house = _pixels(_outline(area.foot[i]), frame)
    m.polygon(house, fill=(230, 60, 50), outline=(150, 20, 20))
    s.line(house + house[:1], fill=(255, 40, 40), width=3)
    out = Image.new("RGB", (2 * PANEL + 12, PANEL + 30), (255, 255, 255))
    out.paste(sat, (0, 30))
    out.paste(plan, (PANEL + 12, 30))
    caption = ImageDraw.Draw(out)
    caption.text((8, 6), "satellite photo", fill=(0, 0, 0), font=_font(16))
    caption.text((PANEL + 20, 6), "street map", fill=(0, 0, 0), font=_font(16))
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def render_driveway(area, i, cands, frame, url):
    """The driveway picture: the satellite photo alone, POINT_PX square, the candidate streets thin and
    yellow, the house outlined in red."""
    img = satellite(frame, url, POINT_PX)
    d = ImageDraw.Draw(img)
    view = area.point[i].buffer((frame[2] - frame[0]) * 0.8)
    for c in cands:
        for part in shapely.get_parts(c["geometry"].intersection(view)):
            if part.geom_type == "LineString":
                d.line(_pixels(part, frame, POINT_PX), fill=(255, 220, 0), width=3)
    house = _pixels(_outline(area.foot[i]), frame, POINT_PX)
    d.line(house + house[:1], fill=(255, 40, 40), width=4)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


# ---------- the model ----------

def ask_openai(endpoint, model, image, prompt, api_key=None, timeout=300, think=False):
    # JSON mode: an answer in under a second instead of an essay that may never reach the JSON; a
    # reasoning model (`think`) writes its reasoning first and its JSON last
    body = {"model": model, "temperature": 0, "max_tokens": 4096 if think else 200,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(image).decode()}}]}]}
    if not think:
        body["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json"} | ({"Authorization": f"Bearer {api_key}"} if api_key else {})
    req = urllib.request.Request(endpoint.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def ask_nearest(order):
    """No model: the nearest street, confident only when the next one is much farther."""
    first = min(range(len(order)), key=lambda k: order[k]["dist"])
    dists = sorted(c["dist"] for c in order)
    sure = len(dists) > 1 and dists[1] > 2 * dists[0] + 20
    return json.dumps({"access": LETTERS[first], "confidence": 90 if sure else 45, "reason": "nearest street (no model)"})


THINK = re.compile(r"(?s)<think>.*?</think>")


def reply_json(text):
    """The JSON a reply gives, past any reasoning: the reply itself, else its last {...} object."""
    text = THINK.sub("", text or "").strip()
    m = re.search(r"[\[{].*[\]}]", text, re.S)
    for chunk in ([m.group(0)] if m else []) + re.findall(r"\{[^{}]*\}", text)[::-1]:
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            continue
    return None


def parse(text, order):
    """(index in `order` or None for "none", confidence, reason) from the model's reply."""
    d = reply_json(text)
    d = d if isinstance(d, dict) else {}
    letter = str(d.get("access", "")).strip().upper()
    conf = d.get("confidence", 0)
    conf = max(0.0, min(100.0, float(conf))) if isinstance(conf, (int, float)) or str(conf).isdigit() else 0.0
    if letter == "NONE":
        return None, conf, str(d.get("reason", ""))[:300]
    if len(letter) == 1 and letter in LETTERS[:len(order)]:
        return LETTERS.index(letter), conf, str(d.get("reason", ""))[:300]
    return "?", 0.0, f"unreadable reply: {(text or '')[:120]}"


def parse_point(text):
    """(x, y) on the driveway picture from the model's reply, None when it sees no way in, "?" when the
    reply cannot be read. A box stands for its centre; a point given in fractions of the picture is
    scaled up."""
    d = reply_json(text)
    if isinstance(d, list):   # [{"point_2d": [x, y], "label": ...}]
        d = d[0] if d and isinstance(d[0], dict) else {}
    if not isinstance(d, dict):
        return "?"
    if str(d.get("seen", "")).lower() in ("none", "no"):
        return None
    xy = d.get("point_2d") or d.get("point") or d.get("bbox_2d")
    if not (isinstance(xy, list) and len(xy) in (2, 4) and all(isinstance(v, (int, float)) for v in xy)):
        return "?"
    x, y = ((xy[0] + xy[2]) / 2, (xy[1] + xy[3]) / 2) if len(xy) == 4 else xy
    return (x * POINT_PX, y * POINT_PX) if max(x, y) <= 1.0 else (x, y)


def point_street(area, i, cands, frame, xy):
    """The candidate (index, metres) nearest the spot pointed at, if within SNAP_M; None for a spot on
    the house itself, where the way in does not meet a street."""
    x0, y0, x1, y1 = frame
    p = shapely.Point(FROM_MERC.transform(x0 + xy[0] / POINT_PX * (x1 - x0), y1 - xy[1] / POINT_PX * (y1 - y0)))
    if area.foot[i].distance(p) < 3:
        return None, None
    d = [c["geometry"].distance(p) for c in cands]
    k = int(np.argmin(d))
    return (k if d[k] <= SNAP_M else None), d[k]


def judge_driveway(area, i, cands, args):
    """Two passes at two zooms, the model pointing at where the way in meets a street: (status,
    choice, confidence, reason, answers). Both passes on one street are applied without review."""
    x0, y0, x1, y1 = area.frame(i, cands)
    cx, cy, half = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2
    picks, answers = [], []
    for scale in (1.0, 1.35):
        frame = (cx - half * scale, cy - half * scale, cx + half * scale, cy + half * scale)
        text = ask_openai(args.endpoint, args.model, render_driveway(area, i, cands, frame, args.imagery),
                          DRIVEWAY_PROMPT.format(size=POINT_PX), args.api_key, think=getattr(args, "think", False))
        answers.append(text)
        xy = parse_point(text)
        if xy is None or xy == "?":
            picks.append(("none" if xy is None else "?", "no way in seen" if xy is None else "unreadable reply"))
            continue
        k, d = point_street(area, i, cands, frame, xy)
        picks.append(("none", "points at the house") if d is None else
                     ("none", f"points {d:.0f} m from the nearest candidate") if k is None else
                     (LETTERS[k], f"points at the way in, {d:.0f} m from {cands[k]['name_fr'] or 'an unnamed street'}"))
    (c1, r1), (c2, r2) = picks
    agree = c1 == c2 and c1 != "?"
    confidence = 90.0 if agree else 0.0
    status = "auto" if agree and confidence >= args.auto else "queue"
    return status, (c1 if c1 != "?" else c2), confidence, r1 if c1 != "?" else r2, answers


def judge_house(area, i, cands, args):
    """Two passes, the letters shuffled: (status, choice, confidence, reason, answers)."""
    if getattr(args, "method", "choose") == "driveway" and args.backend != "nearest":
        return judge_driveway(area, i, cands, args)
    orders = [cands, cands[::-1]]
    picks, answers = [], []
    for order in orders:
        legend = ", ".join(f"{LETTERS[k]} ({COLOR_NAMES[k]})" for k in range(len(order)))
        if args.backend == "nearest":
            text = ask_nearest(order)
        else:
            text = ask_openai(args.endpoint, args.model, render(area, i, cands, order, args.imagery),
                              PROMPT.format(legend=legend), args.api_key, think=getattr(args, "think", False))
        k, conf, reason = parse(text, order)
        answers.append(text)
        canonical = "none" if k is None else "?" if k == "?" else LETTERS[next(j for j, c in enumerate(cands) if c is order[k])]
        picks.append((canonical, conf, reason))
    (c1, f1, r1), (c2, f2, _) = picks
    agree = c1 == c2 and c1 != "?"
    confidence = min(f1, f2) if agree else 0.0
    status = "auto" if agree and confidence >= args.auto else "queue"
    return status, (c1 if c1 != "?" else c2), confidence, r1, answers


# ---------- commands ----------

def make_plan(con, area):
    """Every building with a street within SEARCH_M, the farthest from its nearest street first."""
    (ib, _), dist = area.etree.query_nearest(area.foot, max_distance=SEARCH_M, return_distance=True, all_matches=False)
    order = np.argsort(-dist, kind="stable")
    con.execute("DELETE FROM plan")
    con.executemany("INSERT INTO plan VALUES (?, ?, ?)",
                    [(area.keys[ib[k]], rank, round(float(dist[k]), 1)) for rank, k in enumerate(order)])
    con.commit()
    return len(order)


def run(args):
    con = connect(Path(args.db))
    print("loading the latest build...", flush=True)
    area = Area()
    if not con.execute("SELECT 1 FROM plan LIMIT 1").fetchone():
        print(f"planned {make_plan(con, area):,} buildings, farthest from a street first", flush=True)
    todo = con.execute("""SELECT p.key, p.distance FROM plan p LEFT JOIN judgments j ON j.key = p.key
                          WHERE (j.key IS NULL OR j.status = 'error') AND p.distance >= ? ORDER BY p.rank LIMIT ?""",
                       (args.min_distance, args.limit)).fetchall()
    print(f"{len(todo):,} houses to judge with {args.backend if args.backend == 'nearest' else args.model}; "
          "Ctrl-C to stop, run again to resume", flush=True)
    done, t0 = 0, time.time()
    try:
        for key, dist in todo:
            i = area.index.get(key)
            cands = area.candidates(i) if i is not None else []
            row = {"key": key, "distance": dist, "decided_by": "model", "updated": now(),
                   "model": args.backend if args.backend == "nearest" else
                   args.model + (" (driveway)" if getattr(args, "method", "choose") == "driveway" else "")
                   + (" (think)" if getattr(args, "think", False) else "")}
            if len(cands) < 2:   # one street around: nothing to choose
                row.update(status="single", choice="A" if cands else "none", confidence=None, reason=None,
                           answers=None, context=json.dumps(area.context(i, cands)) if cands else None)
            else:
                try:
                    status, choice, conf, reason, answers = judge_house(area, i, cands, args)
                    row.update(status=status, choice=choice, confidence=conf, reason=reason, answers=json.dumps(answers),
                               context=json.dumps(area.context(i, cands)))
                except (OSError, ValueError, KeyError) as e:   # the model server down, a bad reply
                    row.update(status="error", choice=None, confidence=None, reason=str(e)[:300], answers=None, context=None)
            con.execute("INSERT OR REPLACE INTO judgments (key, status, distance, context, choice, confidence, reason, answers, "
                        "model, decided_by, updated) VALUES (:key, :status, :distance, :context, :choice, :confidence, "
                        ":reason, :answers, :model, :decided_by, :updated)", row)
            con.commit()
            done += 1
            if done % 20 == 0 or row["status"] == "error":
                rate = done / max(time.time() - t0, 1e-6)
                print(f"  {done:,} judged ({rate:.2f}/s), at {dist:.0f} m from a street; last: {key} {row['status']} "
                      f"{row.get('choice')} {row.get('confidence')}", flush=True)
    except KeyboardInterrupt:
        print(f"\nstopped after {done:,}; run again to resume", flush=True)
    print_stats(con)


def stats(con):
    by = dict(con.execute("SELECT status, COUNT(*) FROM judgments GROUP BY status").fetchall())
    planned = con.execute("SELECT COUNT(*) FROM plan").fetchone()[0]
    changes = con.execute("SELECT COUNT(*) FROM judgments WHERE status IN ('auto', 'approved', 'corrected') "
                          "AND choice NOT IN ('none', 'A')").fetchone()[0]
    return {"planned": planned, "judged": sum(by.values()), "by_status": by, "queue": by.get("queue", 0),
            "not_nearest": changes}


def print_stats(con):
    s = stats(con)
    print(f"{s['judged']:,} of {s['planned']:,} planned houses judged: {s['by_status']}; {s['queue']:,} waiting for "
          f"approval; {s['not_nearest']:,} reached from another street than the nearest", flush=True)


# ---------- the approval queue (served by serve.py) ----------

def queue(con, n=10):
    rows = con.execute("SELECT key, distance, context, choice, confidence, reason, model FROM judgments "
                       "WHERE status = 'queue' ORDER BY confidence ASC, distance DESC LIMIT ?", (n,)).fetchall()
    return [{"key": k, "distance": d, "context": json.loads(c), "choice": ch, "confidence": cf, "reason": r, "model": m}
            for k, d, c, ch, cf, r, m in rows]


def decide(con, key, action, letter=None):
    """A person's decision: approve the model's choice, choose another street, none, or skip."""
    row = con.execute("SELECT choice, context FROM judgments WHERE key = ?", (key,)).fetchone()
    if not row:
        raise KeyError(key)
    n = len(json.loads(row[1])["candidates"])
    if action == "approve" and row[0] in LETTERS[:n]:
        status, choice = "approved", row[0]
    elif action == "choose" and letter in LETTERS[:n]:
        status, choice = ("approved" if letter == row[0] else "corrected"), letter
    elif action == "none":
        status, choice = "rejected", "none"
    elif action == "skip":
        status, choice = "skipped", row[0]
    else:
        raise ValueError(action)
    con.execute("UPDATE judgments SET status = ?, choice = ?, decided_by = 'person', updated = ? WHERE key = ?",
                (status, choice, now(), key))
    con.commit()
    return status


def pilot(args):
    """Judge the pilot's houses (PILOT, in a database of their own) and score the answers against the
    person's reading: an answer is right when its letter is among the ones read ("AB": either), and
    a house whose candidates have changed since the reading is left out."""
    rows = [dict(zip(("key", "answer", "certainty", "dists", "candidates", "note"), line.split("\t")))
            for line in PILOT.read_text().splitlines()[1:] if line.strip()]
    con = connect(Path(args.db))
    if not con.execute("SELECT 1 FROM plan LIMIT 1").fetchone():
        con.executemany("INSERT INTO plan VALUES (?, ?, 0)", [(r["key"], rank) for rank, r in enumerate(rows)])
        con.commit()
    run(args)
    done = {k: v for k, *v in con.execute("SELECT key, status, choice, answers, context FROM judgments")}
    tally = {"auto": [0, 0], "queue": [0, 0]}
    agree = changed = changed_right = found = stale = 0
    for r in rows:
        status, choice, answers, context = done.get(r["key"], (None,) * 4)
        cands = json.loads(context)["candidates"] if context else []
        if "/".join(f"{c['dist']:.0f}" for c in cands) != r["dists"]:   # the streets around have changed
            stale += 1
            continue
        if answers and args.method == "driveway":
            agree += status == "auto"   # both zooms on one street, or both seeing no way in
        elif answers:
            a1, a2 = json.loads(answers)
            p1, p2 = parse(a1, cands), parse(a2, cands[::-1])
            agree += p1[0] == p2[0] == "?" or p1[0] is p2[0] is None or (
                isinstance(p1[0], int) and isinstance(p2[0], int) and p1[0] == len(cands) - 1 - p2[0])
        if r["answer"] == "?" or status not in tally:
            continue
        tally[status][0] += choice in r["answer"]
        tally[status][1] += 1
        if status == "auto" and choice not in ("A", "none"):
            changed += 1
            changed_right += choice in r["answer"]
        found += "A" not in r["answer"] and status == "auto" and choice in r["answer"]
    far = [r for r in rows if r["answer"] != "?" and "A" not in r["answer"]]
    print(f"\npilot: {len(rows)} houses, {sum(r['answer'] != '?' for r in rows)} with the way in visible to the person; "
          f"{stale} left out (candidates changed since the reading)")
    print(f"  passes agree on {agree} houses")
    for s, (ok, n) in tally.items():
        print(f"  {s}: right on {ok} of {n} ({100 * ok / max(n, 1):.0f}%)")
    print(f"  answers applied alone that change the street: {changed}, right {changed_right}")
    print(f"  houses reached from a farther street found and applied: {found} of {len(far)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["run", "stats", "plan", "pilot"])
    ap.add_argument("--db", default=None, help="data/judge/judge.sqlite (pilot: one database per model next to PILOT)")
    ap.add_argument("--backend", choices=["openai", "nearest"], default="openai")
    ap.add_argument("--endpoint", default="http://localhost:11434/v1", help="OpenAI-compatible API (Ollama's by default)")
    ap.add_argument("--model", default="qwen2.5vl:7b")
    ap.add_argument("--api-key", default=os.environ.get("JUDGE_API_KEY"),
                    help="the server's API key, if it wants one (Unsloth Studio prints one); or JUDGE_API_KEY")
    ap.add_argument("--imagery", default=IMAGERY, help="satellite tile URL with {z} {x} {y}")
    ap.add_argument("--limit", type=int, default=-1, help="judge at most this many houses this run")
    ap.add_argument("--min-distance", type=float, default=0.0, help="stop at houses this close to a street (metres)")
    ap.add_argument("--auto", type=float, default=AUTO, help="confidence both passes need to skip the queue")
    ap.add_argument("--method", choices=["choose", "driveway"], default="choose",
                    help="choose: pick a lettered street; driveway: point at where the way in meets a street")
    ap.add_argument("--think", action="store_true",
                    help="let a reasoning model think before its JSON answer (no JSON mode; slower)")
    args = ap.parse_args()
    model = args.backend if args.backend == "nearest" else re.sub(r"[^\w.-]+", "_", args.model)
    model += "-driveway" if args.method == "driveway" and args.backend != "nearest" else ""
    model += "-think" if args.think and args.backend != "nearest" else ""
    args.db = args.db or str(PILOT.with_name(f"pilot-{model}.sqlite") if args.command == "pilot" else DB)
    if args.command in ("run", "pilot"):
        (run if args.command == "run" else pilot)(args)
        return
    con = connect(Path(args.db))
    if args.command == "plan":
        print(f"planned {make_plan(con, Area()):,} buildings; judgments kept")
    print_stats(con)


if __name__ == "__main__":
    main()
