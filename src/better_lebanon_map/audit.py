"""Name-quality audit of a finished build: every street, route-only and commune name, in Arabic,
French and English, checked for the defects that make a name read badly.

Usage: uv run python -I -m better_lebanon_map.audit [--viewer viewer] [--interim data/interim]
Prints one line per check with its count and up to five examples, and writes the full list to
data/output/name_audit.json. Exit status 1 if any check other than the informational ones fails.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

from . import translit
from .naming import AR_WAY_WORDS, LATIN_WAY_WORDS
from .network import classify_name
from .translit import FR_CIRCUMFLEX, LETTER_NAMES, latin_matches, strip_accents

AR_LETTERS = re.compile(r"[؀-ۿ]")
LATIN_LETTERS = re.compile(r"[A-Za-zÀ-ÿ]")
FR_TYPE_START = re.compile(r"^(Rue|Route|Impasse|Ruelle|Chemin|Allée|Place|Autoroute|Rond-point|Carrefour|Descente|"
                           r"Sortie|Parvis|Escalier)\b")
EN_TYPE_END = re.compile(r"\b(Street|Road|Lane|Highway|Square|Way|Walk|Junction|Crossing|Roundabout|Stairs)$")
TYPE_WORDS = r"(Rue|Route|Impasse|Avenue|Street|Road|Lane|Avenue|Highway|Path|شارع|طريق|زاروب|جادة|أوتوستراد)"
DOUBLED_TYPE = re.compile(rf"(^|\s){TYPE_WORDS}\s+{TYPE_WORDS}(\s|$)")
REPEATED_WORD = re.compile(r"(?:^|\s)(\S{2,})\s+\1(?:\s|$)")
AR_TYPE_TWICE = re.compile(r"(أوتوستراد|طريق|شارع|جادة)\s(?:.*\s)?(?:ال)?\1(\s|$)")   # "طريق الطريق المقيبلة"
ARABIZI = re.compile(r"[A-Za-z][0-9]+[A-Za-z]")
ODD_SPACING = re.compile(r"\s{2,}|^\s|\s$|\(\s*\)|\s[,.;]|-\s*-")
LOWER_AFTER_ARTICLE = re.compile(r"^\S+ (?:de l'|de la |du |des )[a-zàâçéèêëîïôûùüÿœ]")
FR_ROAD = re.compile(r"^(?:Rue|Route|Autoroute|Passage|Chemin|Impasse|Ruelle|Allée|Boulevard|Avenue|Pont|Tunnel)"
                     r"(?: principale)?(?: de la | de l'| du | des | de | d'| )")
EN_ROAD = re.compile(r" (?:Main )?(?:Road|Street|Highway|Crossing|Lane|Way|Path|Boulevard|Avenue|Passage|Bridge|Tunnel)$")
# Names that come from OSM's tags, or name a place; themes, branches and landmarks are translated
# from the Arabic by construction. Communes are judged on their own, before the gazetteer knows them.
TAGGED = {"osm", "route", "place", "destination"}


def places_of(name, lang):
    """The places a road between places joins ("Route Halba - Minyara"), without its type word."""
    if lang == "ar":
        words = name.split()
        if words and words[0].removeprefix("ال") in AR_WAY_WORDS:
            name = " ".join(words[1:])
        return [p.strip() for p in re.split(r"\s*-\s*", name) if p.strip()]
    name = FR_ROAD.sub("", name) if lang == "fr" else EN_ROAD.sub("", name)
    return [strip_accents(p.strip().lower()) for p in re.split(r"\s+-\s+", name) if p.strip()]


def checks(names):
    """names: list of (kind, id, ar, fr, en). Returns {check: [examples]}."""
    found = {k: [] for k in ("latin_in_arabic", "arabic_in_latin", "english_in_french_order",
                             "french_in_english_order", "doubled_type_word", "repeated_word", "code_as_name",
                             "lowercase_start", "lowercase_after_article", "old_circumflex_spelling", "arabizi",
                             "odd_spacing", "missing_name", "no_street_type", "place_twice")}
    for kind, ident, ar, fr, en in names:
        tag = f"{kind}:{ident}"
        if not all(isinstance(x, str) and x.strip() for x in (ar, fr, en)):
            found["missing_name"].append((tag, ar, fr, en))
            continue
        if LATIN_LETTERS.search(ar):
            found["latin_in_arabic"].append((tag, ar))
        for x in (fr, en):
            if AR_LETTERS.search(x):
                found["arabic_in_latin"].append((tag, x))
        if EN_TYPE_END.search(fr):
            found["english_in_french_order"].append((tag, fr))
        if FR_TYPE_START.match(en):
            found["french_in_english_order"].append((tag, en))
        # A word repeated in every script is the name itself (a person named "Khairallah
        # Khairallah"), and Arabic letter names repeat in a spelled acronym ("دبليو بي سي سي").
        own = all(REPEATED_WORD.search(x) for x in (ar, fr, en))
        for x in (ar, fr, en):
            if DOUBLED_TYPE.search(x) or AR_TYPE_TWICE.search(x):
                found["doubled_type_word"].append((tag, x))
            m = REPEATED_WORD.search(x)
            if m and not own and m.group(1) not in LETTER_NAMES.values():
                found["repeated_word"].append((tag, x))
            if ARABIZI.search(x):
                found["arabizi"].append((tag, x))
            if ODD_SPACING.search(x):
                found["odd_spacing"].append((tag, x))
        for x in (fr, en):
            if x[:1].islower():
                found["lowercase_start"].append((tag, x))
            if any(w.lower() not in FR_CIRCUMFLEX for w in re.findall(r"\w*[âîû]\w*", x)):
                found["old_circumflex_spelling"].append((tag, x))
        if LOWER_AFTER_ARTICLE.match(fr):
            found["lowercase_after_article"].append((tag, fr))
        # Two places in Arabic, one twice in Latin: "Route Dhour El Choueir - Dhour El Choueir" for
        # "طريق ضهور الشوير - الشوير", a commune's Latin name that is another of its localities.
        places_ar = places_of(ar, "ar")
        if len(places_ar) > 1 and len(set(places_ar)) == len(places_ar):
            for x, lang in ((fr, "fr"), (en, "en")):
                p = places_of(x, lang)
                if len(p) > 1 and len(set(p)) < len(p):
                    found["place_twice"].append((tag, ar, x))
                    break
        if kind != "branch" and classify_name(fr)[0] == "generic" and classify_name(ar)[0] == "generic":
            found["code_as_name"].append((tag, ar, fr))
        if kind in ("osm", "route") and not (
                {w.removeprefix("ال") for w in ar.split()} & AR_WAY_WORDS or set(ar.split()) & AR_WAY_WORDS
                or set(re.findall(r"[\w'’-]+", strip_accents(f"{fr} {en}".lower()))) & LATIN_WAY_WORDS):
            found["no_street_type"].append((tag, ar, fr))
    return found


def mismatches(names):
    """Names taken from OSM tags or naming a place whose French and English do not sound like the
    Arabic: another place or person, or a translation the dictionaries do not know. Informational:
    read them."""
    return [(f"{kind}:{ident}", ar, fr, en) for kind, ident, ar, fr, en in names
            if kind in TAGGED and all(isinstance(x, str) for x in (ar, fr, en))
            and not (latin_matches(fr, ar) or latin_matches(en, ar))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--viewer", default="viewer")
    ap.add_argument("--interim", default="data/interim")
    ap.add_argument("--out", default="data/output/name_audit.json")
    args = ap.parse_args()

    # The spellings the pipeline knew, so "sounds like the Arabic" compares with them.
    translit.register_lexicon(json.loads((Path(args.interim) / "lexicon.json").read_text()))
    bounds = json.loads((Path(args.viewer) / "data/boundaries.json").read_text())
    # Communes judged before the gazetteer knows them: with it, each would sound like itself, and a
    # Latin name of another locality ("Kfar Tay Kesrouane" for "دير زرعيا") would go unseen.
    plain = lambda n: re.sub(r"\s*\([^)]*\)$", "", n) if isinstance(n, str) else n
    communes_unlike = [(f"commune:{c['id']}", c["ar"], c["fr"], c["en"]) for c in bounds["communes"]
                       if not (latin_matches(plain(c["fr"]), plain(c["ar"])) or latin_matches(plain(c["en"]), plain(c["ar"])))]
    translit.register_gazetteer((c["ar"], c["fr"], c["en"]) for c in bounds["communes"])
    s = pd.read_parquet(Path(args.interim) / "stage/streets.parquet",
                        columns=["street_id", "name_ar", "name_fr", "name_en", "name_source", "needs_review", "transcribed"])
    s = s[s.name_ar.notna()]
    names = [(src, sid, ar, fr, en) for sid, ar, fr, en, src in
             zip(s.street_id, s.name_ar, s.name_fr, s.name_en, s.name_source)]
    route = json.loads((Path(args.viewer) / "data/route.json").read_text())
    names += [("route", i, ar, fr, en) for i, (ar, fr, en) in enumerate(route["names"])]
    b = json.loads((Path(args.viewer) / "data/boundaries.json").read_text())
    areas = [("commune", c["id"], c["ar"], c["fr"], c["en"]) for c in b["communes"]]
    areas += [(kind, i, a["ar"], a["fr"], a["en"]) for kind in ("districts", "governorates") for i, a in enumerate(b[kind])]
    names += areas

    found = checks(names)
    found["letter_by_letter"] = [("street:" + str(i), ar) for i, ar in zip(s.street_id[s.needs_review.astype(bool)],
                                                                           s.name_ar[s.needs_review.astype(bool)])]
    found["letter_by_letter"] += [("route:" + str(i), route["names"][i][0]) for i in route.get("review", [])]
    info = {"transcribed_from_latin": [("street:" + str(i), ar, fr) for i, ar, fr in
                                       zip(s.street_id[s.transcribed.astype(bool)], s.name_ar[s.transcribed.astype(bool)],
                                           s.name_fr[s.transcribed.astype(bool)])]
                                      + [("route:" + str(i), *route["names"][i][:2]) for i in route.get("transcribed", [])],
            "latin_not_like_arabic": mismatches(names),
            "commune_not_like_arabic": communes_unlike}
    print(f"audited {len(names):,} names: {len(s):,} streets, {len(route['names']):,} route-only names, "
          f"{len(areas):,} communes, districts and governorates")
    failed = 0
    for k, v in {**found, **info}.items():
        failed += len(v) if k in found else 0
        print(f"  {k:26s} {len(v):6d}  {v[:5] if v else ''}")
    Path(args.out).write_text(json.dumps({**found, **info}, ensure_ascii=False, indent=1, default=str))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
