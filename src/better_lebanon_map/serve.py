"""Serve the viewer locally. Like `python -m http.server`, but tells the browser to revalidate
every file, so a re-run of the pipeline or an edit to the viewer shows up on reload. Also serves
the access judge's approval queue (judge.html) and its small JSON API:

  GET  /api/judge/queue?n=10   the least confident judgments waiting for a person
  GET  /api/judge/stats        progress
  POST /api/judge/decide       {"key": "w123", "action": "approve" | "choose" | "none" | "skip", "letter": "B"}

and saves the streets people choose on an address card ("this is the right street"), one line each
in data/corrections/streets.jsonl, which the next build applies (access.load_chosen):

  POST /api/access/choose      {"key": "w123", "junction": [lon, lat], "street": "Rue des Cèdres, Bikfaya"}

Usage: uv run python -m better_lebanon_map.serve [port]
"""

import functools
import http.server
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import judge

VIEWER = Path(__file__).resolve().parents[2] / "viewer"
CHOSEN = VIEWER.parent / "data/corrections/streets.jsonl"


def choose(doc, path=CHOSEN, **source):
    """Records the street a house is reached from, with where the record comes from (`source`);
    raises ValueError on anything else than a building key and a point in Lebanon."""
    key, (lon, lat) = doc["key"], doc["junction"]
    if not re.fullmatch(r"[wr]\d{1,12}", str(key)) or not (35.0 <= float(lon) <= 36.7 and 33.0 <= float(lat) <= 34.7):
        raise ValueError("not a building and a point in Lebanon")
    line = {"key": key, "junction": [round(float(lon), 6), round(float(lat), 6)], "street": str(doc.get("street", ""))[:160],
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **source}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _json(self, doc, status=200):
        body = json.dumps(doc, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/judge/queue":
            n = int(parse_qs(url.query).get("n", ["10"])[0])
            with judge.connect() as con:
                return self._json({"items": judge.queue(con, min(n, 100)), "stats": judge.stats(con)})
        if url.path == "/api/judge/stats":
            with judge.connect() as con:
                return self._json(judge.stats(con))
        if url.path == "/site.json" and not (VIEWER / "site.json").exists():
            return self._json({})   # only a published copy has settings of its own (publish.py)
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/api/judge/decide", "/api/access/choose"):
            return self._json({"error": "not found"}, 404)
        try:
            doc = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 4096)) or b"{}")
            if path == "/api/access/choose":
                choose(doc)
                return self._json({"status": "saved"})
            with judge.connect() as con:
                status = judge.decide(con, doc["key"], doc["action"], doc.get("letter"))
                return self._json({"status": status, "stats": judge.stats(con)})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
            return self._json({"error": str(e)}, 400)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    handler = functools.partial(NoCacheHandler, directory=str(VIEWER))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"Serving {VIEWER} at http://localhost:{port} (access queue: /judge.html)", flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
