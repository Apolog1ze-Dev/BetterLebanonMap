"""Publish the viewer as a static site on GitHub Pages.

The site is the viewer and its data: about 170 MB in 3,000 files (60 MB to upload), nothing to run on a server. It
goes to the `gh-pages` branch of a GitHub repository as one commit that replaces the one before
(a forced push), so the repository does not keep every build. The source can live on the main
branch of the same repository: .gitignore keeps the data out of it.

  uv run python -I -m better_lebanon_map.publish --repo owner/name            # build data/site and report
  uv run python -I -m better_lebanon_map.publish --repo owner/name --push     # and push it to gh-pages

Then, once, in the repository's Settings > Pages: deploy from the branch `gh-pages`, folder `/`.
The map is served at https://owner.github.io/name/.

The published copy differs from the local one (site.json tells the viewer):
- base maps: the viewer's own drawing and OpenStreetMap's tiles. Esri's gray, terrain and satellite
  tiles are offered only with --esri-tiles: their terms cover development, and ask for an ArcGIS
  account beyond it;
- "this is the right street" on an address card opens an issue of the repository with the
  correction, where the local server would save it (corrections.py collects them);
- the access judge's queue (judge.html) is left out: it needs the local server.
"""

import argparse
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL_ONLY = ("judge.html", "judge.js")
MAX_FILE, MAX_SITE = 100 * 2**20, 1000 * 2**20   # GitHub's limits: 100 MB a file, 1 GB a Pages site
NOTICE = """# Better Lebanon Map

The published map of https://github.com/{repo}: an experiment in organising the map of Lebanon so
that people can find their way by address. Its street names and house numbers are a proposal, not
official addressing. Built {built}; this branch holds only the latest build.

The software is (c) 2026 Karim Dagher, under the Apache License 2.0: see LICENSE and NOTICE.

Data derived from OpenStreetMap (c) OpenStreetMap contributors, and from roads Microsoft detected in
satellite imagery (github.com/microsoft/RoadDetections), both under the Open Database License; the
addresses and street names derived from them are available under the same licence. Boundaries (c)
OCHA (COD-AB Lebanon, CC BY-IGO).
"""


def build(repo, site, esri_tiles):
    """Copies the viewer to `site` with its site.json; returns (number of files, bytes, files too big).
    The folder's own .git is kept: it is what lets the next push send only the files that changed."""
    if not (ROOT / "viewer/data/stats.json").exists():
        raise SystemExit("viewer/data is empty: run the pipeline first")
    site.mkdir(parents=True, exist_ok=True)
    for old in site.iterdir():
        if old.name != ".git":
            shutil.rmtree(old) if old.is_dir() else old.unlink()
    shutil.copytree(ROOT / "viewer", site, ignore=shutil.ignore_patterns(*LOCAL_ONLY), dirs_exist_ok=True)
    built = date.today().isoformat()
    bases = ["plain", "osm", *(["light", "terrain", "sat"] if esri_tiles else [])]
    (site / "site.json").write_text(json.dumps({"repo": repo, "bases": bases, "built": built}))
    (site / ".nojekyll").write_text("")   # serve the files as they are, without GitHub's Jekyll build
    (site / "README.md").write_text(NOTICE.format(repo=repo, built=built))
    for name in ("LICENSE", "NOTICE"):   # the viewer's code is published too, under the same licence
        if (ROOT / name).exists():
            shutil.copy(ROOT / name, site / name)
    sizes = {f: f.stat().st_size for f in site.rglob("*") if f.is_file() and ".git" not in f.relative_to(site).parts}
    return len(sizes), sum(sizes.values()), [f for f, size in sizes.items() if size > MAX_FILE]


def push(site, remote, message, author=None):
    """One commit holding the site, pushed over the remote's gh-pages branch: a commit with no
    parent, so the branch only ever holds the latest build. author: "Name <email>" to sign the
    commit with; else git's own identity, else the map's name."""
    def git(*args, capture=False):
        done = subprocess.run(["git", "-C", str(site), *args], check=True, text=True, capture_output=capture)
        return done.stdout.strip() if capture else None

    if not (site / ".git").exists():
        git("init", "--quiet", "--initial-branch", "gh-pages")
    git("remote", "set-url" if "origin" in git("remote", capture=True).split() else "add", "origin", remote)
    git("add", "--all")
    configured = lambda key: subprocess.run(["git", "-C", str(site), "config", key], capture_output=True).returncode == 0
    if author:
        name, _, email = author.partition("<")
        identity = ["-c", f"user.name={name.strip()}", "-c", f"user.email={email.strip(' >')}"]
    elif configured("user.name") and configured("user.email"):
        identity = []
    else:
        identity = ["-c", "user.name=Better Lebanon Map", "-c", "user.email=better-lebanon-map@users.noreply.github.com"]
    commit = git(*identity, "commit-tree", git("write-tree", capture=True), "-m", message, capture=True)
    git("update-ref", "refs/heads/gh-pages", commit)
    git("symbolic-ref", "HEAD", "refs/heads/gh-pages")
    git("push", "--force", "origin", "gh-pages")


def main():
    ap = argparse.ArgumentParser(description="Publish the viewer on GitHub Pages")
    ap.add_argument("--repo", required=True, help="the GitHub repository, as owner/name")
    ap.add_argument("--push", action="store_true", help="push the site to the repository's gh-pages branch")
    ap.add_argument("--remote", help="where to push (default https://github.com/<repo>.git; an SSH URL works too)")
    ap.add_argument("--site", default=str(ROOT / "data/site"), help="where the site is put together")
    ap.add_argument("--esri-tiles", action="store_true", help="also offer Esri's gray, terrain and satellite base maps")
    ap.add_argument("--author", help='who signs the commit, as "Name <email>" (default: git\'s own identity)')
    args = ap.parse_args()
    owner, _, name = args.repo.partition("/")
    if not owner or not name or "/" in name:
        raise SystemExit("--repo must be owner/name")

    site = Path(args.site)
    count, size, too_big = build(args.repo, site, args.esri_tiles)
    print(f"{site}: {count:,} files, {size / 2**20:.0f} MB")
    if too_big or size > MAX_SITE:
        raise SystemExit(f"over GitHub's limits (100 MB a file, 1 GB a site): {[str(f) for f in too_big] or 'the whole site'}")
    url = f"https://{owner}.github.io/{name}/"
    if not args.push:
        print(f"Not pushed. With --push this goes to the gh-pages branch of {args.repo} and is served at {url}")
        return
    stats = json.loads((site / "data/stats.json").read_text())
    push(site, args.remote or f"https://github.com/{args.repo}.git",
         f"Site built {date.today().isoformat()}: {stats['addresses']:,} addresses, {stats['streets']:,} streets", args.author)
    print(f"Pushed. If this is the first time: {args.repo} > Settings > Pages > deploy from branch gh-pages, folder /.\n"
          f"The map is then at {url} (a minute or two after each push).")


if __name__ == "__main__":
    main()
