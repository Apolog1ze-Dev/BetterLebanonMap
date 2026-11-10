"""Street names in Arabic, French and English.

Real OSM names are kept. Streets with no name or a placeholder ("شارع 12") get, in order:
  1. "Route de X" if it is a long road (>= DEST_PRIORITY_M) leading into commune X;
  2. the most notable landmark along it ("Rue de l'Église Mar Elias"), or the hamlet or
     neighbourhood it runs through ("Rue de Haret el Ain");
  3. "Route de X" for shorter roads leading out of the commune;
  4. through streets: a themed name ("Rue des Cèdres"); each sector of the commune around its
     center shares one theme (trees, flowers, birds...), so a theme points to a part of town;
  5. dead-ends and short passages: the street they open onto plus the metric house number at
     the junction, odd on the left and even on the right like houses ("Impasse des Cèdres 231"
     is the dead-end at no. 231 of Rue des Cèdres);
  6. last resort: type + quarter + number ("Rue Achrafié 14").
Every name is unique within its commune.
"""

import math
import re
from collections import defaultdict

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from .localities import METRIC_CRS
from .network import CLASS_RANK, ROUTE_NUMBER, classify_name, normalize
from .themes import THEME_ORDER, THEMES
from .translit import (AR_STREET_TYPES, AR_WORDS, EN_TYPE_NOUNS, STREET_TYPES_FR_EN, ar_street_to_latin, lex_ar_key, ar_to_latin, cap_en, cap_fr, en_to_fr, en_to_fr_street,
                       english_order, fix_ar, fix_en, fix_fr, fr_of, fr_route_to, fr_to_en_street, has_arabic,
                       has_latin, is_transcribed, latin_like, latin_matches,
                       latin_to_ar, looks_english, register_gazetteer, spell_latin_in_arabic, split_bilingual,
                       strip_accents, tidy)

LANDMARK_WEIGHT = {
    "amenity=place_of_worship": 10, "amenity=townhall": 10, "amenity=school": 8, "amenity=university": 8,
    "amenity=college": 8, "amenity=hospital": 8, "amenity=kindergarten": 5, "amenity=library": 6,
    "amenity=marketplace": 6, "amenity=courthouse": 6, "amenity=post_office": 5, "amenity=police": 5,
    "amenity=fire_station": 5, "amenity=community_centre": 5, "leisure=park": 7, "leisure=garden": 6,
    "leisure=stadium": 7, "leisure=sports_centre": 4, "leisure=playground": 3, "tourism=museum": 7,
    "tourism=attraction": 6, "tourism=viewpoint": 5, "natural=spring": 7, "natural=beach": 6,
    "natural=cave_entrance": 5, "natural=peak": 4, "man_made=lighthouse": 7, "man_made=water_tower": 4,
    "man_made=tower": 3, "public_transport=station": 5, "railway=station": 5,
}
HISTORIC_WEIGHT, HISTORIC_MINOR = 7, {"historic=memorial": 5, "historic=ruins": 5}
LANDMARK_MAX_M = 60.0
LANDMARK_MAX_CHARS = 40   # longer landmark names make unwieldy addresses; the street gets another name
PLACE_WEIGHT = {"hamlet": 6, "neighbourhood": 6, "suburb": 6, "quarter": 6}   # not "locality": often a facility
PLACE_MAX_M = 150.0
PRIVATE_RE = re.compile(r"(منزل|فيلا|دكتور|عيادة|مشتل|شركة|\bdr\.?\b|\bvilla\b|\bhouse\b|\bresidence\b|"
                        r"nursery|\bshop\b|\bstore\b|company|\bs\.?a\.?l\b|\bsarl\b|restaurant|resort)", re.I)
# leisure=garden also tags private and commercial gardens; only public ones name a street.
PUBLIC_GARDEN_RE = re.compile(r"(حديقة|منتزه|جنينة|jardin|garden|park|parc)", re.I)
GENERIC_LANDMARK_WORDS = {
    "كنيسه", "مسجد", "جامع", "مدرسه", "ثانويه", "رسميه", "الرسميه", "مستشفي", "بلديه", "حديقه", "ملعب",
    "دير", "مكتبه", "ساحه", "سوق", "نبع", "مركز", "المدرسه", "الكنيسه", "المسجد", "الجامع", "البلديه",
    "school", "church", "mosque", "public", "hospital", "municipality", "park", "garden", "ecole", "école",
    "eglise", "église", "mosquée", "mairie", "municipalité", "de", "la", "le", "l", "the", "of", "playground",
}

DEST_CLASSES = {"trunk", "primary", "secondary", "tertiary", "unclassified"}
DEST_MIN_M, DEST_PRIORITY_M = 400.0, 800.0
NAME_MIN_M = 150.0        # unnamed streets with no buildings get a name only if at least this long
IMPASSE_MAX_M = 250.0     # shorter dead-ends are named after the street they open onto
PASSAGE_MAX_M = 80.0      # so are short connectors between two streets
SECTOR_SIZE = 25          # streets per theme sector

TYPE = {  # kind -> (Arabic, French, English)
    "rue": ("شارع", "Rue", "Street"),
    "route": ("طريق", "Route", "Road"),
    "impasse": ("زاروب", "Impasse", "Lane"),
    "passage": ("ممر", "Passage", "Passage"),
    "chemin": ("درب", "Chemin", "Way"),   # themed names a second and third time, once each theme
    "allee": ("ممشى", "Allée", "Walk"),   # is used up in a very large commune
}
HIGHWAY_NAME = re.compile(r"^(أوتوستراد|اوتوستراد|أتستراد|اتستراد|(?:ال)?طريق السريع)\s")
# Preference when several streets meet a dead-end's open end.
PARENT_RANK = {"osm": 0, "destination": 1, "landmark": 2, "place": 2, "theme": 3, "systematic": 5, "branch": 6}

AR_TYPES = set(AR_STREET_TYPES) | {t[0] for t in TYPE.values()}
FR_TYPES = ("rue", "route", "avenue", "boulevard", "impasse", "ruelle", "passage", "autoroute", "autostrad",
            "place", "corniche", "chemin", "allée", "allee", "escalier", "rond-point", "carrefour", "descente",
            "sortie", "parvis", "montée", "montee", "échangeur", "echangeur", "bahat")   # "Bahat Husseiniyé": باحة
EN_TYPES = ("street", "road", "avenue", "boulevard", "lane", "passage", "highway", "square", "corniche",
            "way", "walk", "stairs", "st", "st.", "rd", "rd.", "junction", "crossing", "roundabout", "descent",
            "exit", "courtyard", "route", "rue", "interchange", "path", "trail", "bridge", "tunnel", "drive",
            "alley", "steps", "entrance")
# Any word that makes a name read as a way, in any script: an OSM name with none of them gets one.
AR_WAY_WORDS = set(AR_TYPES) | {"درب", "ممشى", "سوق", "زقاق", "طلعة", "طلعت", "نزلة", "نزلت", "مدخل", "مخرج", "جسر",
                                "نفق", "مفرق", "كورنيش", "ساحة", "أوتوستراد", "اوتوستراد", "تقاطع", "دوار", "درج"}
LATIN_WAY_WORDS = {strip_accents(w) for w in FR_TYPES + EN_TYPES} | {
    "sentier", "pont", "viaduc", "entree", "quai", "souk", "souq", "bretelle", "voie", "ramp", "gateway", "viaduct"}


def street_kind(highway, length, dead_end):
    if highway in ("trunk", "primary", "secondary") or length >= 1500:
        return "route"
    if dead_end and length < IMPASSE_MAX_M:
        return "impasse"
    if not dead_end and length < PASSAGE_MAX_M and highway not in ("tertiary",):
        return "passage"
    return "rue"


def compose(kind, core, suffix=""):
    t_ar, t_fr, t_en = TYPE[kind]
    tail = f" {suffix}" if suffix else ""
    if core[0].split(" ", 1)[0] == t_ar:   # "درب التبّانة" (the Milky Way) is already a درب: not "درب درب التبّانة"
        return f"{core[0]}{tail}", f"{t_fr} {core[1]}{tail}", f"{core[2]}{tail}"
    # "Our Lady Church Street", not "Church of Our Lady Street"
    en = re.sub(r"^(Church|School|College|Hospital|Mosque|Monastery) of (.+)$", r"\2 \1", core[2])
    fr = re.sub(r"^(Vieux|Vieil|Grand|Nouveau|Nouvel|Ancien|Petit) ", r"du \1 ", core[1])   # "Impasse du Vieux Souk de Hasroun"
    return f"{t_ar} {core[0]}{tail}", f"{t_fr} {fr}{tail}", f"{en} {t_en}{tail}"


def core_of(ar, fr, en):
    """A street name without its type word: 'Rue des Cèdres' -> 'des Cèdres', 'Cedar Street' -> 'Cedar'.
    A highway keeps it ("Impasse de l'Autoroute Beyrouth-Damas 325", not "Impasse Internationale…")."""
    if ar.split(" ", 1)[0] in ("أوتوستراد", "اوتوستراد", "أتستراد", "اتستراد") or fr.lower().startswith("autoroute "):
        return ar, fr_of(fr), en
    head, _, rest = ar.partition(" ")
    ar_core = rest if head in AR_TYPES and rest else ar
    words = fr.split(" ", 1)
    fr_core = words[1] if len(words) == 2 and words[0].lower() in FR_TYPES else fr
    words = en.rsplit(" ", 1)
    if len(words) == 2 and words[1].lower() in EN_TYPES:
        en_core = words[0]
    else:
        lead = en.split(" ", 1)
        en_core = lead[1] if len(lead) == 2 and lead[0].lower() in FR_TYPES else en
    # A dead-end off "Route principale de Mastita" is "Impasse Mastita 1437", not "Impasse principale…".
    ar_core = re.sub(r"\s+(?:ال)?(?:رئيسي|رئيسية|عام)$|^(?:ال)?عام\s+", "", ar_core).strip() or ar_core
    fr_core = re.sub(r"^principale?\s+(?:de la |de l'|du |des |de |d')?", "", fr_core, flags=re.I).strip() or fr_core
    en_core = re.sub(r"\s+Main$|^Main\s+", "", en_core).strip() or en_core
    if ar_core.removeprefix("ال") in AR_TYPES or fr_core.lower() in ("principale", "principal") or en_core == "Main":
        return None   # "الشارع الرئيسي" (Main Street): nothing left to name a branch after
    if " - " in fr_core or " - " in ar_core or re.search(r"(?i)\b(rue|route|avenue)\b", fr_core) \
            or re.fullmatch(r"\d+(st|nd|rd|th)", en_core):
        return None   # a road between two places, "1ère Rue Principale": no "Impasse 1ère Rue Principale 899"
    return ar_core, fr_core, en_core


def osm_name(name):
    """An OSM street name without the route number some carry ("شارع حارة حريك (96)"); the first
    of several ("Rue des Jardins;Rue des Oliviers")."""
    return ROUTE_NUMBER.sub("", name.split(";")[0]).strip() if isinstance(name, str) else name


def latin_tag(name):
    """An OSM name:fr / name:en tag, unless it is only a municipal number or code ("Rue 42"), an
    identifier ("Street_uni_1") or Arabizi ("Ch7e7ir")."""
    name = osm_name(tidy(name))
    if not isinstance(name, str) or "_" in name or re.search(r"[A-Za-z][0-9]+[A-Za-z]", name) or has_arabic(name):
        return None   # also a name:fr tag written in Arabic ("مسجد حوش")
    return name if classify_name(name)[0] == "real" else None


def with_type(ar, fr, en):
    """OSM Latin tags missing the street-type word of the Arabic name: "شارع واصف بارودي" tagged
    "Wassef Baroudi" -> "Rue Wassef Baroudi" / "Wassef Baroudi Street"."""
    fr_type, en_type = AR_STREET_TYPES.get(ar.split(" ", 1)[0], (None, None)) if has_arabic(ar) else (None, None)
    if not has_arabic(ar) and isinstance(fr, str):   # "Rue Hiram" tagged "Hiram" in English
        en_type = dict((f.lower(), e) for f, e in STREET_TYPES_FR_EN).get(fr.split(" ", 1)[0].lower())
    if fr_type and isinstance(fr, str) and not set(fr.lower().split()) & set(FR_TYPES):   # "Vieille route de Saïda"
        fr = f"{fr_type} {fr_of(fr)}"
    words = en.lower().split() if isinstance(en, str) else []
    if en_type and words and not set(words) & set(EN_TYPES) and words[0] not in FR_TYPES:
        en = f"{en} {en_type}"   # not when a type is already there ("Coastal Road Fadous")
    return fr, en


FRENCH_WORDS_LEFT = re.compile(r"(?i)(^|\s)(de|du|des|la|le|les|d'|l')(\s|$)|\b(d|l)'")


def with_way_word(ar, fr, en):
    """An OSM name with no street type in any script reads as an address with one: "Antoine
    Choueiri" -> "Rue Antoine Choueiri" / "شارع انطوان شويري"; a road between places, "الوردانية -
    كفرنبرخ", or to one, "تنورين" -> "Route Wardaniyeh - Kfar Nabrakh", "Route de Tannourine"."""
    if not all(isinstance(x, str) and x for x in (ar, fr, en)):
        return ar, fr, en
    latin = set(re.findall(r"[\w'’-]+", strip_accents(f"{fr} {en}".lower())))
    # Between two places a souk is a village: "سوق الغرب" in "بسابا - سوق الغرب" is no street type.
    ar_types, latin_types = (AR_WAY_WORDS - {"سوق"}, LATIN_WAY_WORDS - {"souk", "souq"}) if " - " in ar \
        else (AR_WAY_WORDS, LATIN_WAY_WORDS)
    if {w.removeprefix("ال") for w in ar.split()} & ar_types or set(ar.split()) & ar_types or latin & latin_types:
        return ar, fr, en
    sources = []
    ar_to_latin(ar, "fr", None, sources)
    if " - " in ar or " - " in fr:
        return f"طريق {ar}", f"Route {fr}", f"{en} Road"
    if sources and set(sources) == {"gazetteer"}:
        return f"طريق {ar}", f"Route {fr_route_to(fr)}", f"{en} Road"
    return f"شارع {ar}", f"Rue {fr_of(fr)}", f"{en} Street"


def _two_places(tag, ar):
    """A Latin tag joining two places with a bare hyphen, as the Arabic separates them: "Bsaba-Souk
    el Gharb" for "بسابا - سوق الغرب" -> "Bsaba - Souk el Gharb" (not "Saint-Joseph")."""
    if not isinstance(tag, str) or " - " in tag or tag.count("-") != 1:
        return tag
    left, right = (p.strip() for p in tag.split("-"))
    a_left, a_right = (p.strip() for p in ar.split(" - ", 1))
    a_left = re.sub(r"^(?:طريق|شارع|أوتوستراد) ", "", a_left)
    return f"{left} - {right}" if latin_matches(left, a_left) and latin_matches(right, a_right) else tag


def osm_trilingual(name, name_fr, name_en):
    """(ar, fr, en, guessed, transcribed) for a real OSM street name and its name:fr / name:en tags."""
    name = fix_ar(osm_name(name))
    tag_fr, tag_en = fix_fr(latin_tag(name_fr)), fix_en(english_order(latin_tag(name_en)))
    if looks_english(tag_fr):   # name:fr "Sea Highway": English, not French
        tag_en, tag_fr = tag_en or fix_en(english_order(tag_fr)), None
    if has_latin(name) and not has_arabic(name):   # "Cardinal Jebrayel Tabbouni" tagged "Alfred Naccache Road"
        tag_fr, tag_en = (t if t is None or latin_like(t, name) else None for t in (tag_fr, tag_en))
        if isinstance(tag_fr, str) and tag_fr.split(" ", 1)[0].lower() in FR_TO_AR_TYPE \
                and not set(re.findall(r"[\w'’-]+", strip_accents(name.lower()))) & LATIN_WAY_WORDS:
            name = tag_fr   # "Hortance Tamer" tagged "Rue Hortance Tamer": a street in Arabic and English too
    if has_arabic(name) and (isinstance(tag_fr, str) or isinstance(tag_en, str)):
        # A tag naming something else ("Jal El Dib Highway" on أوتوستراد البحر, tagged "Autoroute de
        # la Mer" in French) gives way to the other tag, or to the Arabic name when the dictionaries
        # know every word of it.
        fr_ok, en_ok = latin_matches(tag_fr, name), latin_matches(tag_en, name)
        if fr_ok or en_ok:
            tag_fr, tag_en = (tag_fr if fr_ok else None), (tag_en if en_ok else None)
        else:
            report = []
            ar_street_to_latin(name, "fr", report)
            tag_fr, tag_en = (None, None) if not report else (tag_fr, tag_en)
    if has_arabic(name) and " - " in name:
        tag_fr, tag_en = (_two_places(t, name) for t in (tag_fr, tag_en))
    head = tag_fr.split(" ", 1)[0].lower() if isinstance(tag_fr, str) else None
    if has_arabic(name) and head in FR_TO_AR_TYPE \
            and not {w.removeprefix("ال") for w in name.split()} & (AR_WAY_WORDS | set(AR_STREET_TYPES)):
        name = f"{FR_TO_AR_TYPE[head]} {name}"   # "جوزيف شادر" tagged "Rue Joseph Chader"; not "نفق … - أوتوستراد البحر"
    tag_fr, tag_en = with_type(name, tag_fr, tag_en)
    ar, fr, en, guessed = trilingual(name, None, tag_fr, tag_en)
    if has_arabic(name) and not (isinstance(tag_fr, str) and isinstance(tag_en, str)):
        # The missing Latin name comes from the dictionaries when they know every word, else
        # from OSM's other Latin name (its own spelling), else letter by letter (to review).
        guessed = False
        fr_type = AR_STREET_TYPES.get(name.split(" ", 1)[0], (None,))[0]
        for lang, have, other in (("fr", tag_fr, tag_en), ("en", tag_en, tag_fr)):
            if isinstance(have, str):
                continue
            report, sources = [], []
            spelled = ar_street_to_latin(name, lang, report, sources)
            # English from the Arabic when curated translations give every word ("Lebanon Street",
            # "Coastal Highway"); otherwise it follows the French tag's spelling ("Mqaïblé Main
            # Road", not the lexicon's "Muqeible"), unless French words would be left in it.
            curated = not report and set(sources) <= {"dictionary", "reviewed", "gazetteer"}
            from_fr = fix_en(fr_to_en_street(other)) if lang == "en" and isinstance(other, str) else None
            if from_fr and not curated and not FRENCH_WORDS_LEFT.search(from_fr):
                spelled, report = from_fr, []
            elif report and isinstance(other, str):
                spelled, report = (en_to_fr_street(other, fr_type) if lang == "fr" else fr_to_en_street(other)), []
            guessed = guessed or bool(report)
            fr, en = (spelled, en) if lang == "fr" else (fr, spelled)
    if not isinstance(tag_en, str):
        en = fr_to_en_street(en)   # a French name standing in for English: "Rue Sassoun" -> "Sassoun Street"
    ar, fr, en = with_way_word(fix_ar(ar), fix_fr(fr), fix_en(en))
    if isinstance(ar, str) and isinstance(en, str) and ar.startswith(("أوتوستراد", "اوتوستراد")):
        en = re.sub(r" (?:Street|Road)$", " Highway", en)   # an autostrade is a highway in every script
    return spell_latin_in_arabic(fix_ar(ar)), cap_fr(fix_fr(fr)), cap_en(fix_en(en)), guessed, is_transcribed(name)


def trilingual(name, ar, fr, en):
    """(ar, fr, en, uncertain?) from OSM name tags, filling missing scripts. A filled name is
    uncertain only when some word had to be spelled letter by letter."""
    name, fr, en = tidy(name), tidy(fr), tidy(en)
    fr, en = (x if has_latin(x) and not has_arabic(x) else None for x in (fr, en))   # name:fr written in Arabic
    both_ar, both_latin = split_bilingual(name)   # "Lady Stanhope Ruins آثارات لايدي ستانهوب"
    if both_ar:
        name, ar, fr = both_ar, ar if isinstance(ar, str) else both_ar, fr or both_latin
    ar = ar if isinstance(ar, str) else (name if has_arabic(name) else None)
    latin = name if has_latin(name) and not has_arabic(name) else None
    if isinstance(en, str) and classify_name(en)[0] != "real":
        en = None   # "Street 54" on Rue Nicolas Ghosn: a municipal number, not a translation
    en = en if isinstance(en, str) else latin
    if fr is None and ar and not _guessed(ar, "fr"):   # from the Arabic when every word is known
        fr = ar_to_latin(ar, "fr")
    # A Latin `name` is often English ("Bikfaya Police Station", "Saghbine Main Road"): give French
    # its own word order.
    fr = fr if isinstance(fr, str) else (en_to_fr_street(en_to_fr(en)) if isinstance(en, str) else None)
    en = en or fr
    report = []
    if ar is None and (latin or fr or en):
        # From the street's own name, not from a translation tag that may name someone else.
        ar = latin_to_ar(latin or en or fr, report)
    if fr is None and ar:
        fr = ar_to_latin(ar, "fr", report)
    if en is None and ar:
        en = ar_to_latin(ar, "en", report)
    return spell_latin_in_arabic(fix_ar(ar)), cap_fr(fix_fr(fr)), cap_en(fix_en(en)), bool(report)


def _landmark_weight(kind):
    if kind in LANDMARK_WEIGHT:
        return LANDMARK_WEIGHT[kind]
    if kind.startswith("historic="):
        return HISTORIC_MINOR.get(kind, HISTORIC_WEIGHT)
    return 0


STREET_NAME_START = re.compile(r"^(rue|route|avenue|boulevard|impasse|place|street|road|شارع|طريق|جادة|زاروب|ساحة)\b",
                               re.IGNORECASE)


def _not_a_place_name(name):
    """A street's own name ("Rue Foch"), a code ("MM2") or Arabizi ("mashrou3 day3a"): never the
    name of a landmark or hamlet a street could be named after."""
    n = name.strip()
    return bool(STREET_NAME_START.match(n) or classify_name(n)[0] != "real"
                or re.search(r"[A-Za-z][0-9]+[A-Za-z]|^[A-Za-z]{1,4}\d+$", n))


FR_TO_AR_TYPE = {"rue": "شارع", "route": "طريق", "avenue": "جادة", "boulevard": "جادة", "impasse": "زاروب",
                 "autoroute": "أوتوستراد"}
# English written in Arabic letters ("ثانوية كفرشيما هايسكول"), and words that betray a name left
# in the other language ("Rue The Cross", "Église Saint-Joseph Street").
AR_ENGLISH = {"هاي", "سكول", "هايسكول", "ناشونال", "انترناشونال", "إنترناشونال", "انترناشيونال", "إنترناشيونال",
              "كولدج", "كوليج", "يونيفرسيتي", "سنتر", "بارك", "البارك", "ستريت", "مول", "سيتي", "أكاديمي", "اكاديمي",
              "إنستيتيوت", "هاوس", "كلوب", "ستيشن", "بلازا", "تاور", "غاردن", "كافيه", "ماركت", "سوبرماركت"}
EN_MARKERS = {"the", "of", "and", "school", "church", "university", "municipality", "street", "road", "high", "lady",
              "our", "cross", "college", "national", "international"}
FR_MARKERS = {"de", "du", "des", "la", "le", "les", "église", "école", "collège", "université", "municipalité", "rue",
              "route", "et", "lycée", "sœur", "père", "mosquée", "hôpital"}


LANDMARK_NOUNS = {lex_ar_key(a).replace("ة", "ه") for a, (f, e) in AR_WORDS.items() if e in EN_TYPE_NOUNS}
FACILITY_NOUNS = {"ملعب", "مقبره", "جامعه", "مدرسه", "مستشفي", "مستشفى", "معمل", "مصنع", "محطه", "ثكنه"}


def _clean_landmark(h, ar, fr, en):
    """A landmark name usable for a street: named in Arabic in OSM, no English in Arabic letters,
    no word of the wrong language, not a list or description."""
    words = lambda s: set(re.findall(r"[\w'’-]+", s.lower()))
    return (has_arabic(h.name) or has_arabic(h.name_ar)) and not (set(ar.split()) & AR_ENGLISH) \
        and not ({w.strip("'’") for w in words(fr)} & EN_MARKERS - {"national", "international"}) \
        and not (words(en) & FR_MARKERS) and "," not in ar + fr + en and "،" not in ar


def _guessed(ar, lang):
    report = []
    ar_to_latin(ar, lang, report)
    return bool(report)


def _is_specific(name):
    words = re.split(r"[\s\-']+", normalize(name))
    return len(name) >= 3 and not name.strip().isdigit() and any(w not in GENERIC_LANDMARK_WORDS for w in words if w)


def landmark_candidates(landmarks, edges):
    """Best landmark per street: each landmark names only the street it is closest to."""
    lm = landmarks.to_crs(METRIC_CRS).copy()
    lm["weight"] = lm.kind.map(_landmark_weight)
    lm = lm[(lm.weight > 0) & lm["name"].map(lambda n: isinstance(n, str) and _is_specific(n)
                                              and not PRIVATE_RE.search(n) and not _not_a_place_name(n))]
    garden = lm.kind == "leisure=garden"
    lm = lm[~garden | lm["name"].map(lambda n: bool(PUBLIC_GARDEN_RE.search(n)))].reset_index(drop=True)
    e = edges[edges.street_id >= 0]
    tree = shapely.STRtree(e.geometry.values)
    (il, ie), d = tree.query_nearest(lm.geometry.values, max_distance=LANDMARK_MAX_M,
                                     return_distance=True, all_matches=False)
    hits = lm.iloc[il].copy()
    hits["street_id"] = e.street_id.values[ie]
    hits["score"] = hits.weight - d / 15
    out = {}
    for h in hits.sort_values("score", ascending=False).itertuples():
        if h.street_id in out:
            continue
        names = landmark_names(h)
        # Only a landmark whose name the dictionaries know word by word names a street; any other
        # street gets a themed name instead.
        if names:
            ar, fr, en = names
            out[h.street_id] = (h.score, "landmark", (ar, fr_of(fr), en), False, f"{h.osm_type}/{h.osm_id}")
    return out


def landmark_names(h):
    """(ar, fr, en) for a landmark named in Arabic as a landmark noun plus words the reviewed table,
    the gazetteer or the dictionary know ("كنيسة مار الياس" -> "Église Mar Elias" / "Mar Elias
    Church"), translated from the Arabic alone: OSM's Latin tags for landmarks are too often half
    translated. None otherwise."""
    ar = next((n for n in (h.name_ar, h.name) if isinstance(n, str) and has_arabic(n)), None)
    if not ar:
        return None
    ar = fix_ar(re.sub(r"\s+", " ", ar).strip())
    words = ar.split()
    first = lex_ar_key(words[0]).replace("ة", "ه") if words else ""
    if not 2 <= len(words) <= 5 or not (first in LANDMARK_NOUNS or first.removeprefix("ال") in LANDMARK_NOUNS) \
            or set(words) & AR_ENGLISH or not _clean_landmark(h, ar, "", ""):
        return None
    if first.removeprefix("ال") == "ساحه" or re.search(r"[0-9٠-٩]", ar):
        return None   # a square is a street of its own; "كنيسة سيدة البحر 15" is not a name
    if any(lex_ar_key(w).replace("ة", "ه").removeprefix("ال") in LANDMARK_NOUNS for w in words[1:]):
        return None   # "كنيسة مدرسة سيدة الجمهور", a church of a school: no clean name in French or English
    sources, report = [], []
    fr, en = ar_to_latin(ar, "fr", report, sources), ar_to_latin(ar, "en", report, sources)
    # Dictionary words only (type nouns, saints, first names, adjectives): a place word is too often
    # misread ("مستشفى البرج" in Bourj el-Barajneh is not in Borj Akkar).
    if report or not set(sources) <= {"dictionary"} \
            or max(len(fr), len(en), len(ar)) > LANDMARK_MAX_CHARS:
        return None
    if first == "كليه":   # كلية named after a saint or a person is a school, "Collège Mar Youssef", not a faculty
        fr, en = re.sub(r"\bFaculté\b", "Collège", fr, count=1), re.sub(r"\bFaculty\b", "College", en, count=1)
    return spell_latin_in_arabic(ar), cap_fr(fix_fr(fr)), cap_en(fix_en(en))


def place_candidates(places, edges, streets, communes):
    """Hamlets and neighbourhoods name the most important unnamed street passing within PLACE_MAX_M."""
    usable = places["name"].map(lambda n: isinstance(n, str) and not _not_a_place_name(n)
                                and lex_ar_key(n.split()[0]).replace("ة", "ه") not in LANDMARK_NOUNS | FACILITY_NOUNS)
    pl = places[places.place.isin(PLACE_WEIGHT) & usable].to_crs(METRIC_CRS).reset_index(drop=True)
    commune_keys = set(communes.name_ar.map(normalize)) | set(communes.name_fr.map(normalize))
    e = edges[edges.street_id >= 0]
    importance = streets.set_index("street_id")["spine_length"]
    eligible = set(streets.loc[streets.needs_name, "street_id"])
    tree = shapely.STRtree(e.geometry.values)
    ip, ie = tree.query(pl.geometry.values, predicate="dwithin", distance=PLACE_MAX_M)
    out = {}
    for p_idx in np.unique(ip):
        p = pl.iloc[p_idx]
        ar, fr, en, guessed = trilingual(p["name"], p["name_ar"], p["name_fr"], p["name_en"])
        if ar and fr and not latin_matches(fr, ar, every=True):   # "Hay Zahlé Mar Elias" for "حي مار إلياس"
            report = []
            fr, en = cap_fr(fix_fr(ar_to_latin(ar, "fr", report))), cap_en(fix_en(ar_to_latin(ar, "en", report)))
            guessed = guessed or bool(report)
        if guessed or is_transcribed(p["name"]) or not (ar and fr and en) or normalize(ar) in commune_keys \
                or normalize(fr) in commune_keys:
            continue
        cands = {sid for sid in e.street_id.values[ie[ip == p_idx]] if sid in eligible}
        if not cands:
            continue
        sid = max(cands, key=lambda k: importance[k])
        score = PLACE_WEIGHT[p["place"]]
        if sid not in out or out[sid][0] < score:
            # "Rue du Nouveau Secteur" for a common noun, "Rue de Haret el-Ain" for a name
            out[sid] = (score, "place", (ar, fr_of(fr) if fr_of(fr) != fr else fr_route_to(fr), en), guessed,
                        f"node/{p['osm_id']}")
    return out


def destination_candidates(streets, neighbors, communes):
    c = communes.set_index("commune_id")
    out = {}
    for s, nb in zip(streets.itertuples(), neighbors):
        if not nb or s.highway not in DEST_CLASSES or s.spine_length < DEST_MIN_M:
            continue
        nb = [cid for cid in nb if c.at[cid, "town_fr"] != c.at[s.commune_id, "town_fr"]]   # not within one city
        if not nb:
            continue
        best = max(nb, key=lambda cid: (c.at[cid, "rank"], c.at[cid, "area_km2"]))
        out[s.street_id] = (c.at[best, "town_ar"], fr_route_to(c.at[best, "town_fr"]), c.at[best, "town_en"], best)
    return out


class Namer:
    """Holds the per-commune name registry and writes names onto the streets frame."""

    def __init__(self, s):
        self.s = s
        self.taken = defaultdict(set)        # commune -> normalized Arabic full names
        self.cores = {}                      # row index -> (core triple, suffix)
        self.pools = {}                      # commune -> theme names still free

    @staticmethod
    def keys(names):
        """Registry keys for a name in each language: unique in Arabic, French and English."""
        return {f"{lang}:{re.sub(r'[^\w]|_', '', normalize(strip_accents(n)))}" for lang, n in zip("afe", names)}

    def free(self, cid, names):
        return not (self.keys(names) & self.taken[cid])

    def take(self, cid, names):
        self.taken[cid] |= self.keys(names)

    def set(self, i, kind, core, suffix, source, ref, guessed=False):
        ar, fr, en = compose(kind, core, suffix)
        self.take(self.s.at[i, "commune_id"], (ar, fr, en))
        self.cores[i] = (core, suffix)
        self.s.loc[i, ["name_ar", "name_fr", "name_en", "name_source", "name_ref", "needs_review"]] = \
            [ar, fr, en, source, ref, guessed]


def _theme_pools(namer, cid):
    """Theme names still free in a commune: first with the street's own type, then as "Chemin"."""
    if cid not in namer.pools:
        s = namer.s
        taken = {(core_of(*names) or names)[0]
                 for names in s.loc[(s.commune_id == cid) & s.name_ar.notna(), ["name_ar", "name_fr", "name_en"]].values}
        namer.pools[cid] = [
            {t: [e for e in THEMES[t] if e[0] not in taken] for t in THEME_ORDER},
            {t: list(THEMES[t]) for t in THEME_ORDER},
            {t: list(THEMES[t]) for t in THEME_ORDER},
        ]
    return namer.pools[cid]


def _assign_themes(namer, idx, communes):
    """Themed names by angular sector around the commune center; returns streets left over."""
    s = namer.s
    centers = communes.set_index("commune_id")["center"]
    overflow = []
    sub = s.loc[idx]
    if sub.empty:
        return overflow
    mids = shapely.line_interpolate_point(sub.spine.values, 0.5, normalized=True)
    sub = sub.assign(mx=shapely.get_x(mids), my=shapely.get_y(mids),
                     importance=sub.spine_length + 20 * sub.building_count)
    for cid, grp in sub.groupby("commune_id"):
        c = centers[cid]
        own, second, third = _theme_pools(namer, cid)
        angle = np.arctan2(grp.my - c.y, grp.mx - c.x)
        grp = grp.assign(angle=angle).sort_values("angle")
        k = min(len(THEME_ORDER), max(1, math.ceil(len(grp) / SECTOR_SIZE)))
        sectors = np.array_split(grp.index.values, k)
        order = np.argsort([-grp.loc[sec, "importance"].sum() for sec in sectors])
        for theme, sec in zip(THEME_ORDER, [sectors[j] for j in order]):
            for i in grp.loc[sec].sort_values("importance", ascending=False).index:
                placed = False
                # The sector's own theme first, then whichever has most names left; once every
                # theme is used, the same names again as "Chemin des Cèdres" / "درب الأرز".
                for pools, kind in ((own, s.at[i, "kind"]), (second, "chemin"), (third, "allee")):
                    for pool_key in [theme] + sorted(pools, key=lambda t: -len(pools[t])):
                        while pools[pool_key] and not placed:
                            entry = pools[pool_key].pop(0)
                            if namer.free(cid, compose(kind, entry)):
                                namer.set(i, kind, entry, "", "theme", f"theme/{pool_key}")
                                s.at[i, "kind"] = kind
                                placed = True
                        if placed:
                            break
                    if placed:
                        break
                if not placed:
                    overflow.append(i)
    return overflow


def _assign_branches(namer, idx, edges):
    """Dead-ends and passages take the name of the street they open onto + junction house number."""
    s = namer.s
    by_node = defaultdict(set)
    xy = {}
    for sid, u, v, g in zip(edges.street_id.values, edges.u.values, edges.v.values, edges.geometry.values):
        c = shapely.get_coordinates(g)
        xy[u], xy[v] = c[0], c[-1]
        if sid >= 0:
            by_node[u].add(sid)
            by_node[v].add(sid)
    row_of = dict(zip(s.street_id.values, s.index.values))
    numbers_on = defaultdict(set)
    pending = sorted(idx, key=lambda i: s.at[i, "street_id"])
    while pending:
        progress, still = False, []
        for i in pending:
            r = s.loc[i]
            ends = [r.start_node] if r.kind == "impasse" and not r.start_dead_end else \
                [r.end_node] if r.kind == "impasse" else [r.start_node, r.end_node]
            best = None
            for node in ends:
                for sid in by_node[node] - {r.street_id}:
                    j = row_of[sid]
                    if not isinstance(s.at[j, "name_ar"], str) or j not in namer.cores and s.at[j, "name_source"] != "osm":
                        continue
                    if j in namer.cores and "-" in namer.cores[j][1]:
                        continue   # at most two levels ("Impasse des Cèdres 360-45"); deeper ones get a theme
                    if HIGHWAY_NAME.match(str(s.at[j, "name_ar"])) or str(s.at[j, "name_fr"]).startswith("Autoroute"):
                        continue   # a lane off a motorway gets a name of its own, not "… Highway Lane 1354"
                    if j not in namer.cores and core_of(s.at[j, "name_ar"], s.at[j, "name_fr"], s.at[j, "name_en"]) is None:
                        continue   # nor does a lane off a street called just "Main Street"
                    key = (PARENT_RANK.get(s.at[j, "name_source"], 9), -CLASS_RANK.get(s.at[j, "highway"], 0),
                           -s.at[j, "spine_length"])
                    if best is None or key < best[0]:
                        best = (key, j, node)
            if best is None:
                still.append(i)
                continue
            _, j, node = best
            parent = s.loc[j]
            junction = shapely.Point(xy[node])
            d = parent.spine.project(junction)
            L = parent.spine.length
            a = parent.spine.interpolate(max(d - 1, 0))
            b = parent.spine.interpolate(min(d + 1, L))
            into = r.spine.interpolate(min(15, r.spine.length) if node == r.start_node
                                       else max(r.spine.length - 15, 0))
            cross = (b.x - a.x) * (into.y - junction.y) - (b.y - a.y) * (into.x - junction.x)
            left = cross > 0
            if j in namer.cores:
                core, parent_suffix = namer.cores[j]
            else:
                core, parent_suffix = core_of(parent.name_ar, parent.name_fr, parent.name_en), ""
            n = max(int(round(d)), 1)
            if (n % 2 == 1) != left:
                n += 1
            while True:  # next free number of the same parity
                suffix = f"{parent_suffix}-{n}" if parent_suffix else str(n)
                if n not in numbers_on[j] and namer.free(r.commune_id, compose(r.kind, core, suffix)):
                    break
                n += 2
            numbers_on[j].add(n)
            namer.set(i, r.kind, core, suffix, "branch",
                      f"branch/{parent.street_id}/{n}/{'left' if left else 'right'}")
            progress = True
        if not progress:
            return still
        pending = still
    return []


def _assign_systematic(namer, idx, communes, quarters, state):
    """Last resort: type + quarter + number, numbered outward from the quarter center. Placeholder
    streets ("شارع 52") keep their old number when it is free."""
    s = namer.s
    if not len(idx):
        return
    c = communes.set_index("commune_id")
    q = quarters.set_index("quarter_id")
    fb = s.loc[idx].copy()
    fb["scope"] = fb.quarter_id.where(fb.quarter_id.notna(), fb.commune_id)
    mids = fb.spine.interpolate(0.5, normalized=True)
    centers = [q.at[sc, "center"] if sc in q.index else c.at[sc, "center"] for sc in fb.scope]
    fb["center_dist"] = mids.distance(gpd.GeoSeries(centers, index=fb.index, crs=METRIC_CRS))
    for scope, grp in fb.groupby("scope"):
        names = q.loc[scope] if scope in q.index else c.loc[scope]
        held, assigned = state["reserved"].get(scope, set()), state["assigned"][scope]
        keep = grp[grp.old_number.notna()].sort_values("spine_length", ascending=False)
        rest = grp.drop(keep.index).sort_values("center_dist")
        core = (names.name_ar, names.name_fr, names.name_en)
        free = lambda i, num: num not in assigned and namer.free(
            s.at[i, "commune_id"], compose(s.at[i, "kind"], core, str(num)))
        for i, r in keep.iterrows():
            num = int(r.old_number)
            if not free(i, num):
                rest = pd.concat([rest, keep.loc[[i]]])
                continue
            assigned.add(num)
            namer.set(i, s.at[i, "kind"], core, str(num), "systematic", f"scope/{scope}")
        n = 0
        for i in rest.index:
            n += 1
            while n in held or not free(i, n):
                n += 1
            assigned.add(n)
            namer.set(i, s.at[i, "kind"], core, str(n), "systematic", f"scope/{scope}")


def register_places(communes, quarters, places):
    """The gazetteer of place names that names are spelled with: communes, quarters, and hamlets and
    neighbourhoods with a Latin name in OSM, when that name is theirs ("الوطى" is not "Wata El
    Moussaitbeh"). Also needed before writing outputs from a stored stage."""
    register_gazetteer(zip(communes.name_ar, communes.name_fr, communes.name_en))
    register_gazetteer(zip(quarters.name_ar, quarters.name_fr, quarters.name_en))
    fr = places.name_fr.where(places.name_fr.notna(), places.name_en)
    en = places.name_en.where(places.name_en.notna(), fr)
    own = [latin_matches(f, a) for f, a in zip(fr, places["name"])]
    register_gazetteer(zip(places["name"][own], fr[own], en[own]))


def name_streets(streets, edges, landmarks, places, communes, quarters, neighbors):
    register_places(communes, quarters, places)
    s = streets.copy()
    s["dead_end"] = s.start_dead_end | s.end_dead_end
    s["kind"] = [street_kind(h, L, d) for h, L, d in zip(s.highway, s.spine_length, s.dead_end)]
    s["needs_name"] = (s.name_status != "real") & (
        (s.building_count > 0) | ((s.spine_length >= NAME_MIN_M) & (s.highway != "service")))
    for col in ("name_ar", "name_fr", "name_en", "name_source", "name_ref"):
        s[col] = None
    s["needs_review"] = False
    s["transcribed"] = False   # Arabic transcribed from a Latin-only OSM name (spellings.TRANSCRIBED_LATIN)
    s["old_name"] = s.osm_name.where(s.name_status == "generic")
    namer = Namer(s)

    real = s.name_status == "real"
    for i in s.index[real]:
        r = s.loc[i]
        ar, fr, en, guessed, transcribed = osm_trilingual(r.osm_name, r.osm_name_fr, r.osm_name_en)
        s.loc[i, ["name_ar", "name_fr", "name_en", "name_source", "needs_review", "transcribed"]] = \
            [ar, fr, en, "osm", guessed, transcribed]
        namer.take(r.commune_id, (ar, fr, en))

    # Two real streets of one commune whose OSM French or English names collide (one street
    # tagged "طلعة نيو روضة", another "طلعة جديدة روضة", both "Rue Nouvelle Raouda"): the longer keeps
    # it, the others are spelled from their own Arabic name.
    rows = s.index[real & s.name_ar.notna()]
    for col, lang in (("name_fr", "fr"), ("name_en", "en")):
        key = s.loc[rows, col].map(lambda n: re.sub(r"[^\w]|_", "", normalize(strip_accents(n))))
        clash = key.duplicated(keep=False) & key.groupby([s.loc[rows, "commune_id"], key]).transform("size").gt(1)
        for _, grp in s.loc[rows[clash.values]].groupby([s.loc[rows[clash.values], "commune_id"], key[clash]]):
            for n, i in enumerate(grp.sort_values("spine_length", ascending=False).index):
                if n == 0 or not has_arabic(s.at[i, "osm_name"]):
                    continue
                report = []
                s.at[i, col] = ar_street_to_latin(osm_name(s.at[i, "osm_name"]), lang, report)
                s.at[i, "needs_review"] = bool(s.at[i, "needs_review"]) or bool(report)
    namer.taken.clear()
    for i in rows:
        namer.take(s.at[i, "commune_id"], tuple(s.loc[i, ["name_ar", "name_fr", "name_en"]]))

    named_here = landmark_candidates(landmarks, edges)
    for sid, cand in place_candidates(places, edges, s, communes).items():
        if sid not in named_here or named_here[sid][0] < cand[0]:
            named_here[sid] = cand
    dest = destination_candidates(s, neighbors, communes)

    todo = s[s.needs_name].sort_values("spine_length", ascending=False)
    rest = []
    for i, r in todo.iterrows():
        options = []
        d = dest.get(r.street_id)
        lm = named_here.get(r.street_id)
        if d and r.spine_length >= DEST_PRIORITY_M:
            options.append(("route", d[:3], "destination", f"commune/{d[3]}", False))
        if lm:
            options.append((r.kind, lm[2], lm[1], lm[4], lm[3]))
        if d and r.spine_length < DEST_PRIORITY_M:
            options.append(("route", d[:3], "destination", f"commune/{d[3]}", False))
        for kind, core, source, ref, guessed in options:
            if namer.free(r.commune_id, compose(kind, core)):
                s.at[i, "kind"] = kind
                namer.set(i, kind, core, "", source, ref, guessed)
                break
        else:
            rest.append(i)

    rest = s.loc[rest]
    themed = rest.index[rest.kind.isin(["rue", "route"])]
    branches = rest.index[rest.kind.isin(["impasse", "passage"])]
    generic = s[s.name_status == "generic"]
    state = {
        "reserved": generic.assign(scope=generic.quarter_id.where(generic.quarter_id.notna(), generic.commune_id))
        .groupby("scope").old_number.agg(lambda v: set(v.dropna().astype(int))).to_dict(),
        "assigned": defaultdict(set),
    }
    overflow = _assign_themes(namer, themed, communes)
    _assign_systematic(namer, overflow, communes, quarters, state)
    orphans = _assign_branches(namer, branches, edges)
    # Dead-ends opening onto no named street (a track, a ramp) get a themed name of their own.
    orphans = _assign_themes(namer, orphans, communes)
    _assign_systematic(namer, orphans, communes, quarters, state)

    # Every name in its script and case: Latin letters left in Arabic names spelled in Arabic
    # ("WBCC" -> "دبليو بي سي سي"), French and English names capitalised.
    s["name_ar"] = s.name_ar.map(spell_latin_in_arabic)
    s["name_fr"], s["name_en"] = s.name_fr.map(cap_fr), s.name_en.map(cap_en)

    # Last guarantee that every address is unique: two separate streets of one commune that OSM
    # tags alike keep their name with north/south (or west/east) of each other added.
    sides = {"name_ar": ("شمال", "جنوب", "غرب", "شرق"), "name_fr": ("Nord", "Sud", "Ouest", "Est"),
             "name_en": ("North", "South", "West", "East")}
    letters = lambda n: re.sub(r"[^\w]|_", "", normalize(strip_accents(n))) if isinstance(n, str) else None
    # First try spelling the colliding language from the street's own other names (OSM tags two
    # roads "Broumana Main Road" in English; "طريق برمانا" can be "Broumana Road"). The shortest
    # street changes first; the longest keeps the name unless it alone can change.
    arabic = lambda r: osm_name(r.osm_name) if has_arabic(r.osm_name) else None
    rederive = {
        "name_en": (lambda r: fr_to_en_street(r.name_fr) if isinstance(r.name_fr, str) else None,
                    lambda r: ar_street_to_latin(arabic(r), "en") if arabic(r) else None),
        "name_fr": (lambda r: ar_street_to_latin(arabic(r), "fr") if arabic(r) else None,
                    lambda r: en_to_fr_street(r.name_en) if isinstance(r.name_en, str) else None),
        "name_ar": (lambda r: latin_to_ar(r.name_fr) if isinstance(r.name_fr, str) else None,
                    lambda r: latin_to_ar(r.name_en) if isinstance(r.name_en, str) else None),
    }
    # Not for two streets named alike in every language (one OSM name on two separate roads):
    # respelling one language would leave "Route de la Mer" and "Route Sea" for the same طريق البحر.
    whole = [s[c].map(letters) for c in ("name_ar", "name_fr", "name_en")]
    twin = s.groupby([s.commune_id, *whole]).name_ar.transform("size").gt(1)
    for col in ("name_ar", "name_fr", "name_en"):
        key = s[col].map(letters)
        clash = key.notna() & key.groupby([s.commune_id, key]).transform("size").gt(1)
        for (cid, _), grp in s[clash].groupby([s.commune_id[clash], key[clash]]):
            taken = set(key[s.commune_id == cid].dropna())
            sharing = len(grp)
            for i in grp.sort_values("spine_length").index:
                if sharing == 1:
                    break
                if twin[i]:
                    continue
                for derive in rederive[col]:
                    alt = derive(s.loc[i])
                    if alt and letters(alt) not in taken:
                        s.at[i, col], key.at[i] = alt, letters(alt)
                        taken.add(letters(alt))
                        sharing -= 1
                        break
    for col in ("name_ar", "name_fr", "name_en"):
        key = s[col].map(letters)
        clash = key.notna() & key.groupby([s.commune_id, key]).transform("size").gt(1)
        for _, grp in s[clash].groupby([s.commune_id[clash], key[clash]]):
            mids = shapely.line_interpolate_point(grp.spine.values, 0.5, normalized=True)
            xs, ys = shapely.get_x(mids), shapely.get_y(mids)
            vertical = (ys.max() - ys.min()) >= (xs.max() - xs.min())
            for rank, pos in enumerate(np.argsort(-ys if vertical else xs)):
                i = grp.index[pos]
                for c, words in sides.items():
                    side = words[(0 if vertical else 2) + rank] if len(grp) == 2 else str(rank + 1)
                    s.at[i, c] = f"{s.at[i, c]} ({side})"

    s["duplicate_name"] = False
    for col in ("name_ar", "name_fr", "name_en"):
        key = s[col].map(lambda n: re.sub(r"[^\w]|_", "", normalize(strip_accents(n))) if isinstance(n, str) else None)
        s["duplicate_name"] |= key.notna() & key.groupby([s.commune_id, key]).transform("size").gt(1)
    s.loc[s.duplicate_name, "needs_review"] = True
    return s
