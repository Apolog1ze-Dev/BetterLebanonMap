"""Learn how Lebanese name words are spelled in the other script, from OSM itself.

About 10,000 Lebanese places, shops, schools and streets in OpenStreetMap carry a name in Arabic
and in French or English. Words whose translation is already known ("شارع"/"Rue",
"مدرسة"/"School") are set aside; when both sides then have the same number of words, they are
paired in order ("وادي أبو جميل" / "Ouadi Abou Jmil"). A pairing is kept only when the two sound
alike (their consonant skeletons agree), and the most frequent spelling of each word wins. The
result is a small statistical transliteration model learned from real Lebanese usage, used
before falling back to letter-by-letter spelling.
"""

import json
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher

from .translit import (AR_STREET_TYPES, AR_WORDS, EN_TRAILING_TYPES, EN_TYPE_NOUNS, lex_ar_key, lex_lat_key,
                       strip_accents)

AR_DIACRITICS = re.compile(r"[ً-ْـٰ]")
ARTICLES = {"al", "el", "ad", "ed", "ar", "er", "as", "es", "ash", "ech", "az", "ez", "at", "an", "ul"}
# Type words (street, school, pharmacy...) are set aside before pairing; names never are, or
# "صلاح الدين" / "Salaheddine" would pair "صلاح" with the whole name.
TYPE_AR = set(AR_STREET_TYPES) | {ar for ar, (fr, en) in AR_WORDS.items() if en in EN_TYPE_NOUNS} | {
    "صيدلية", "مطعم", "فرن", "محطة", "سوبرماركت", "ملحمة", "مخبز", "مقهى", "فندق", "مصرف", "بنك", "مستودع",
    "معمل", "شركة", "مؤسسة", "متجر", "محل", "ملعب", "مدرسة", "ثانوية", "مسجد", "جامع", "كنيسة", "دير", "حي",
    "زاروب", "ممر", "ساحة", "مستشفى", "مستوصف", "بلدية", "جامعة", "معهد", "مكتبة", "نادي", "مركز",
}
TYPE_LATIN = {w.lower() for w in EN_TRAILING_TYPES} | {
    "pharmacie", "pharmacy", "restaurant", "boulangerie", "bakery", "station", "supermarket", "supermarche",
    "boucherie", "butcher", "cafe", "hotel", "bank", "banque", "company", "shop", "store", "mosque", "mosquee",
    "church", "eglise", "school", "ecole", "college", "lycee", "hospital", "hopital", "municipality", "municipalite",
    "street", "rue", "road", "route", "avenue", "boulevard", "impasse", "square", "place", "lane", "of", "de", "du",
    "des", "la", "le", "les", "the", "and", "et", "center", "centre", "club", "garden", "park", "stadium",
}
# Arabic letter -> consonant class, for "do these two words sound alike?"
AR_SKELETON = {
    "ب": "b", "ت": "t", "ث": "t", "ج": "j", "ح": "h", "خ": "k", "د": "d", "ذ": "d", "ر": "r", "ز": "z",
    "س": "s", "ش": "s", "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "غ": "g", "ف": "f", "ق": "k", "ك": "k",
    "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "w", "ي": "y",
}
LATIN_DIGRAPHS = [("sch", "s"), ("ch", "s"), ("sh", "s"), ("kh", "k"), ("gh", "g"), ("th", "t"), ("dh", "d"),
                  ("ph", "f"), ("ou", "w"), ("oo", "w"), ("ee", "y"), ("q", "k"), ("c", "k"), ("x", "ks"),
                  ("v", "f"), ("p", "b"), ("g", "j")]


ar_key, lat_key = lex_ar_key, lex_lat_key


def _ar_skeleton(word):
    w = ar_key(word)
    w = w[2:] if w.startswith("ال") and len(w) > 3 else w
    return "".join(AR_SKELETON.get(c, "") for c in w).replace("w", "").replace("y", "")


def _lat_skeleton(word):
    w = lat_key(word)
    w = re.sub(r"^(al|el|ad|ed|ar|er|as|es|ash|ech|az|ez|at|an|ul)-", "", w)
    for a, b in LATIN_DIGRAPHS:
        w = w.replace(a, b)
    w = re.sub(r"(.)\1", r"\1", w)              # doubled letters are one Arabic letter
    return re.sub(r"[aeiouyw'\-]", "", w)


def sounds_alike(ar, lat):
    a, b = _ar_skeleton(ar), _lat_skeleton(lat)
    if not a or not b:
        return False
    if a[0] != b[0] and not ({a[0], b[0]} <= set("kgj") or {a[0], b[0]} <= set("hk")):
        return False
    if min(len(a), len(b)) / max(len(a), len(b)) < 0.7:
        return False
    return SequenceMatcher(None, a, b).ratio() >= 0.7


def _ar_tokens(text):
    words = [w for w in re.split(r"[\s\-،,()/]+", AR_DIACRITICS.sub("", text)) if w]
    return [w for w in words if re.search(r"[؀-ۿ]", w) and ar_key(w) not in TYPE_AR]


def _lat_tokens(text):
    raw = [w for w in re.split(r"[\s\-,()/]+", text) if w]
    out, i = [], 0
    while i < len(raw):
        k = lat_key(raw[i])
        if k in ARTICLES and i + 1 < len(raw):
            out.append(f"{raw[i]}-{raw[i + 1]}")   # "el Hayek" -> "el-Hayek", like "الحايك"
            i += 2
            continue
        out.append(raw[i])
        i += 1
    return [w for w in out if re.search(r"[A-Za-zÀ-ÿ]", w) and lat_key(w) not in TYPE_LATIN]


def learn(pairs):
    """pairs: iterable of (arabic, french, english) -> lexicon dict."""
    ar_lat = {"fr": defaultdict(Counter), "en": defaultdict(Counter)}
    lat_ar = defaultdict(Counter)
    for ar, fr, en in pairs:
        a = _ar_tokens(ar)
        for lang, latin in (("fr", fr), ("en", en)):
            if not isinstance(latin, str) or not a:
                continue
            l = _lat_tokens(latin)
            if len(l) != len(a):
                continue
            for x, y in zip(a, l):
                if sounds_alike(x, y):
                    ar_lat[lang][ar_key(x)][y] += 1
                    lat_ar[lat_key(y)][x] += 1
                    bare = re.sub(r"^(al|el|ad|ed|ar|er|as|es|ash|ech|az|ez|at|an|ul)-", "", lat_key(y))
                    if bare != lat_key(y):
                        lat_ar[bare][x] += 1
    best = lambda counter: counter.most_common(1)[0][0]
    return {
        "fr": {k: best(v) for k, v in ar_lat["fr"].items()},
        "en": {k: best(v) for k, v in ar_lat["en"].items()},
        "ar": {k: best(v) for k, v in lat_ar.items()},
    }


def build(bilingual, path=None):
    lex = learn(zip(bilingual.ar, bilingual.fr, bilingual.en))
    if path:
        with open(path, "w") as f:
            json.dump(lex, f, ensure_ascii=False, indent=0)
    return lex
