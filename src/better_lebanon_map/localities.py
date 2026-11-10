"""Communes (scope for numbering and name uniqueness), districts, governorates and quarters.

Communes are the 1,610 official cadastral villages (المناطق العقارية) from OCHA's Common
Operational Dataset for Lebanon (COD-AB v02, reviewed October 2025, CC BY-IGO), which cover
the whole country. Arabic and English names come from that dataset; French names, centers and
settlement rank from the matching OpenStreetMap commune or village node. The 17 areas OCHA
marks as contested between cadasters ("Conflict") join the neighbour they share the longest
border with, and are also kept apart so the map can show them.

Districts are OCHA's 26; each belongs to the governorate OpenStreetMap places it in (9,
including Keserwan-Jbeil, created in 2017), and governorate outlines are dissolved from the
districts so all boundary lines agree. Beirut's sectors (OSM admin_level=8) are quarters.
"""

import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from .translit import (ar_to_latin, fix_ar, has_arabic, latin_matches, latin_to_ar, modern_spelling, same_sounds,
                       sounds_like, strip_accents)

METRIC_CRS = "EPSG:32636"
PLACE_RANK = {"city": 3, "town": 2, "village": 1}
COD_AB_DIR = Path("data/raw/cod_ab")
MATCH_SHARE = 0.6   # an OSM commune covering this much of a cadaster lends it its names


def _names(df):
    """Arabic/French/English display names, filling gaps by transliteration."""
    ar = df["name_ar"].where(df["name_ar"].notna(), df["name"].where(df["name"].map(has_arabic)))
    fr = df["name_fr"].fillna(df["name_en"]).fillna(df["name"].where(~df["name"].map(has_arabic)))
    en = df["name_en"].fillna(df["name_fr"]).fillna(df["name"].where(~df["name"].map(has_arabic)))
    ar = ar.fillna(fr.map(lambda s: latin_to_ar(s) if isinstance(s, str) else None))
    fr = fr.fillna(ar.map(lambda s: ar_to_latin(s, "fr"))).map(modern_spelling)   # "Bhamdoûn" -> "Bhamdoun"
    en = en.fillna(ar.map(lambda s: ar_to_latin(s, "en"))).map(modern_spelling)
    return pd.DataFrame({"name_ar": ar, "name_fr": fr, "name_en": en}, index=df.index)


def _key(name):
    """Comparison key: no diacritics, no Arabic article on any word, no spaces or punctuation."""
    if not isinstance(name, str):
        return None
    s = re.sub(r"[ً-ْـ]", "", name.lower())
    s = re.sub(r"(^|[\s\-])ال", r"\1", s)
    s = re.sub(r"[\s\-'’]", "", s)
    return s.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"}))


def _same_place(place, cadaster, district):
    """A village node names the same place as a cadaster: equal names, or the official name is
    the village name plus its district ("عين عرب مرجعيون"), never a neighbourhood ("صيدا الدكرمان")."""
    kp, kc, kd = _key(place), _key(cadaster), _key(district)
    if not kp or not kc:
        return False
    return kp == kc or (bool(kd) and kc in (kp + kd, kd + kp))


def _similar(a, b):
    ka, kb = _key(a), _key(b)
    return bool(ka) and bool(kb) and len(min(ka, kb, key=len)) >= 3 and (ka in kb or kb in ka)


def _best_overlap(polys, others, key_cols):
    """For each polygon, the row of `others` covering the largest share of it (>= MATCH_SHARE)."""
    j = gpd.overlay(polys[["pid", "geometry"]], others[key_cols + ["geometry"]], how="intersection", keep_geom_type=True)
    j["share"] = j.area / polys.set_index("pid").loc[j.pid].area.values
    j = j[j.share >= MATCH_SHARE].sort_values("share").drop_duplicates("pid", keep="last")
    return j.set_index("pid")


def _absorb(pieces, communes):
    """Merge each piece into the commune it shares the longest border with."""
    geoms = list(communes.geometry.values)
    tree = shapely.STRtree(geoms)
    for piece in pieces:
        ring = piece.buffer(5)
        cand = tree.query(ring, predicate="intersects")
        if len(cand):
            overlap = [shapely.area(shapely.intersection(geoms[i], ring)) for i in cand]
            target = cand[int(np.argmax(overlap))]
        else:
            target = tree.nearest(piece)
        geoms[target] = shapely.union(geoms[target], piece)
    communes = communes.copy()
    communes["geometry"] = [shapely.make_valid(g) for g in geoms]
    return communes


def _centers(communes, villages):
    """Village/town/city node of the same name inside each commune, else OCHA's label point."""
    hits = gpd.sjoin(villages, communes[["geometry"]], predicate="within", how="inner")
    centers, ranks, pops, fr, en, ar = [], [], [], [], [], []
    for idx, row in communes.iterrows():
        cand = hits[hits.index_right == idx]
        same = cand[[_same_place(n, row["name_ar"], row["adm2_ar"]) or _key(f) == _key(row["name_en"])
                     for n, f in zip(cand["name"], cand["name_fr"])]]
        if same.empty:
            centers.append(row["label_point"])
            ranks.append(1)
            pops.append(None)
            fr.append(None)
            en.append(None)
            ar.append(None)
            continue
        best = same.distance(row["label_point"]).idxmin()
        centers.append(same.geometry.loc[best])
        ranks.append(PLACE_RANK.get(same.at[best, "place"], 1))
        pops.append(same.at[best, "population"])
        fr.append(same.at[best, "name_fr"])
        en.append(same.at[best, "name_en"])
        ar.append(same.at[best, "name_ar"] if isinstance(same.at[best, "name_ar"], str) else same.at[best, "name"])
    return centers, ranks, pops, fr, en, ar


def article_usage(names):
    """How often each Arabic word appears in OSM names, to tell "الدامور" from "روميه"."""
    from collections import Counter
    return Counter(w for n in names if isinstance(n, str)
                   for w in re.split(r"[\s\-،,()/]+", re.sub(r"[ً-ْـ]", "", n)) if w)


def build(admin, places, cod_dir=COD_AB_DIR, usage=None):
    admin = admin.to_crs(METRIC_CRS)
    places = places.to_crs(METRIC_CRS)
    villages = places[places.place.isin(PLACE_RANK)].reset_index(drop=True)
    a3 = gpd.read_file(Path(cod_dir) / "lbn_admin3.geojson").to_crs(METRIC_CRS)
    a2 = gpd.read_file(Path(cod_dir) / "lbn_admin2.geojson").to_crs(METRIC_CRS).reset_index(drop=True)

    # OCHA marks areas contested between cadasters "Conflict" or "Litige". Unnamed ones join a
    # neighbour; the two with a name of their own stay communes. All are shown as contested.
    disputed = a3.adm3_name.isin(["Conflict", "Litige"])
    contested = a3[disputed]
    cad = a3[~disputed | a3.adm3_name1.notna()].reset_index(drop=True)
    cad["adm3_name"] = cad.adm3_name.where(~cad.adm3_name.isin(["Conflict", "Litige"]), None)
    pieces = a3[disputed & a3.adm3_name1.isna()]
    communes = gpd.GeoDataFrame({
        "pid": cad.adm3_pcode.values, "osm_id": None, "name": cad.adm3_name1.values,
        "name_ar": cad.adm3_name1.values, "name_en": cad.adm3_name.values, "name_fr": None,
        "adm2_pcode": cad.adm2_pcode.values, "adm2_ar": cad.adm2_name1.values, "adm2_en": cad.adm2_name.values,
        "adm1_name": cad.adm1_name.values,
        "label_point": gpd.points_from_xy(cad.center_lon, cad.center_lat, crs=4326).to_crs(METRIC_CRS),
        "geometry": cad.geometry.values,
    }, crs=METRIC_CRS)

    # OCHA's Arabic name is authoritative. The usual French/English spelling is borrowed from the
    # OSM commune or village node on the same cadaster only when its Arabic name agrees.
    cod_en = communes.name_en.fillna("").str.replace(r"\s*N:\s*(\d+)", r" \1", regex=True).str.strip()
    communes["name_en"] = cod_en.where(cod_en != "", None)
    osm7 = admin[admin.admin_level == 7].reset_index(drop=True)
    match = _best_overlap(communes, osm7.assign(oname=osm7["name"], oname_fr=osm7.name_fr, oname_en=osm7.name_en,
                                                oid=osm7.osm_id), ["oname", "oname_fr", "oname_en", "oid"])
    agree = pd.Series([_similar(match.oname.get(pid), ar) for pid, ar in zip(communes.pid, communes.name_ar)],
                      index=communes.index)
    osm_fr = communes.pid.map(match.oname_fr).where(agree)
    osm_en = communes.pid.map(match.oname_en).where(agree)
    communes["osm_id"] = communes.pid.map(match.oid).where(agree)
    centers, ranks, pops, place_fr, place_en, place_ar = _centers(communes, villages)
    communes["center"] = gpd.GeoSeries(centers, index=communes.index, crs=METRIC_CRS)
    communes["rank"], communes["population"] = ranks, pops
    borrowed_fr = osm_fr.fillna(pd.Series(place_fr, index=communes.index))
    borrowed_en = osm_en.fillna(pd.Series(place_en, index=communes.index))
    # Two cadasters of one district must not end up with the same borrowed name (Saida and
    # Saida Dekermane both "Sidon"): those keep OCHA's own spelling.
    clash = borrowed_fr.notna() & borrowed_fr.duplicated(keep=False) & \
        borrowed_fr.groupby([borrowed_fr, communes.adm2_pcode]).transform("size").gt(1)
    borrowed_fr[clash], borrowed_en[clash] = None, None
    communes["ocha_en"] = communes.name_en
    communes["name_en"] = borrowed_en.fillna(communes.name_en)
    communes["name_fr"] = borrowed_fr.fillna(communes.name_en)
    communes[["name_ar", "name_fr", "name_en"]] = _names(communes).values
    for col in ("name_fr", "name_en"):
        communes[col] = communes[col].map(_ocha_latin)
    place_ar = pd.Series(place_ar, index=communes.index)
    # Latin names from an OSM object whose Arabic name is the cadaster's ("صور" / "Tyr") are its own.
    vouched = osm_fr.notna() | pd.Series([_same_place(p, a, d) if isinstance(p, str) else False
                                          for p, a, d in zip(place_ar, communes.name_ar, communes.adm2_ar)],
                                         index=communes.index)
    _readable_names(communes, communes.pid.map(match.oname).where(agree), place_ar, usage)
    _consistent_names(communes, place_ar, vouched)

    communes = _absorb(list(pieces.geometry.values), communes)
    communes["center"] = gpd.GeoSeries(communes["center"].values, index=communes.index, crs=METRIC_CRS)
    contested_union = contested.geometry.union_all()
    communes["contested_km2"] = communes.geometry.intersection(contested_union).area / 1e6
    communes["source"] = "cadaster"
    communes["osm_geometry"] = gpd.GeoSeries([None] * len(communes), index=communes.index, crs=METRIC_CRS)
    communes["commune_id"] = [f"C{i:04d}" for i in range(len(communes))]
    communes["area_km2"] = communes.area / 1e6
    communes["kind"] = communes["rank"].map({3: "city", 2: "town", 1: "village"})
    communes.loc[communes.adm1_name == "Beirut", "kind"] = "quarter"

    # Districts (OCHA) named after the matching OSM district; governorates from OSM, drawn
    # by dissolving their districts so every line coincides.
    osm5 = admin[admin.admin_level == 5].reset_index(drop=True)
    osm4 = admin[admin.admin_level == 4].reset_index(drop=True)
    osm4_names = _names(osm4)
    a2["pid"] = a2.adm2_pcode
    dmatch = _best_overlap(a2, osm5.assign(dn=osm5["name"], dn_ar=osm5.name_ar, dn_fr=osm5.name_fr, dn_en=osm5.name_en),
                           ["dn", "dn_ar", "dn_fr", "dn_en"])
    gj = gpd.overlay(a2[["pid", "geometry"]], osm4[["geometry"]].assign(g=range(len(osm4))), how="intersection",
                     keep_geom_type=True)
    gj["a"] = gj.area
    gov_of = gj.sort_values("a").drop_duplicates("pid", keep="last").set_index("pid")["g"]
    districts = gpd.GeoDataFrame({
        "pid": a2.pid.values, "name": a2.pid.map(dmatch.dn).fillna(a2.adm2_name1).values,
        "name_ar": a2.pid.map(dmatch.dn_ar).values, "name_fr": a2.pid.map(dmatch.dn_fr).values,
        "name_en": a2.pid.map(dmatch.dn_en).fillna(a2.adm2_name).values,
        "gov": a2.pid.map(gov_of).values, "geometry": a2.geometry.values,
    }, crs=METRIC_CRS)
    beirut = a2.adm1_name.values == "Beirut"
    for lang in ("ar", "fr", "en"):   # Beirut has no district of its own: use the governorate's name
        districts.loc[beirut, f"name_{lang}"] = osm4_names[f"name_{lang}"].values[districts.loc[beirut, "gov"].astype(int)]
    districts[["name_ar", "name_fr", "name_en"]] = _names(districts).values
    # OSM's names in the style of the others ("Caza de Tyr"), with Saïda / Saida as street names and
    # road signs write it, not "Sidon".
    districts["name_fr"] = districts.name_fr.str.replace(r"^Caza ", "District ", regex=True) \
        .str.replace(r"\bSidon\b", "Saïda", regex=True)
    districts["name_en"] = districts.name_en.str.replace(r"\bSidon\b", "Saida", regex=True)
    govs = districts.dissolve(by="gov").reset_index()
    govs = gpd.GeoDataFrame({
        "name": osm4["name"].values[govs.gov.astype(int)],
        "name_ar": osm4_names.name_ar.values[govs.gov.astype(int)],
        "name_fr": osm4_names.name_fr.values[govs.gov.astype(int)],
        "name_en": osm4_names.name_en.values[govs.gov.astype(int)],
        "geometry": govs.geometry.values,
    }, crs=METRIC_CRS)
    gov_index = {g: i for i, g in enumerate(districts.dissolve(by="gov").index)}

    d_index = {p: i for i, p in enumerate(districts.pid)}
    communes["district_idx"] = communes.adm2_pcode.map(d_index).astype(int)
    communes["governorate_idx"] = districts.gov.values[communes.district_idx].astype(int)
    communes["governorate_idx"] = communes.governorate_idx.map(gov_index).astype(int)
    for lang in ("ar", "fr", "en"):
        communes[f"district_{lang}"] = districts[f"name_{lang}"].values[communes.district_idx]
        communes[f"governorate_{lang}"] = govs[f"name_{lang}"].values[communes.governorate_idx]
    communes.loc[communes.adm1_name == "Beirut", "district_idx"] = -1
    communes["region_fr"] = communes["district_fr"]

    q = admin.loc[admin.admin_level == 8].copy().reset_index(drop=True)
    qn = _names(q)
    quarters = gpd.GeoDataFrame({
        "quarter_id": [f"Q{i:03d}" for i in range(len(q))],
        "name_ar": qn["name_ar"], "name_fr": qn["name_fr"], "name_en": qn["name_en"],
        "center": q.geometry.representative_point(), "geometry": q.geometry,
    }, crs=METRIC_CRS)
    areas = {"governorates": govs, "districts": districts.drop(columns=["gov"]),
             "contested": contested[["geometry"]].reset_index(drop=True)}
    _disambiguate(communes)
    _towns(communes)
    return communes.drop(columns=["label_point"]), quarters, areas


# Words that never make a village name on their own: "Kafr" is OCHA's truncated "Kafr el-Ftouh".
NAME_PREFIXES = {"kafr", "kfar", "ain", "aïn", "aain", "deir", "beit", "mazraat", "mazraet", "ras", "haret", "tell",
                 "tall", "wadi", "ouadi", "khirbet", "majdel", "majdal", "qornet", "jouret", "mrah", "haouch", "dahr",
                 "borj", "nabi", "mar", "zouk", "zouq", "mchaa", "abou"}
AR_PREFIXES = {"راس", "رأس", "عين", "كفر", "دير", "بيت", "حارة", "مزرعة", "تل", "وادي", "خربة", "مجدل", "قرنة", "جورة",
               "مراح", "حوش", "ضهر", "برج", "النبي", "مار", "ذوق", "مشاع", "أبو", "ابو"}
LATIN_ARTICLES = {"el", "al", "ed", "es", "ez", "et", "en", "er", "ech", "ej", "ad", "as", "az", "de", "du", "des",
                  "of", "the", "and"}   # "Port of Beirut" is not "Port of" in the Beirut district
# Villages always written with the article whose bare form is also a common word ("مختارة": chosen).
ALWAYS_ARTICLE = {"مختارة", "رمادية"}
# Cities whose cadastral pieces are named "Trablous Ez-Zeitoun", "Zahleh El-Maallaqa"...: roads
# lead to the city ("Route de Tripoli"), not to the piece.
CITY_GROUPS = {"trablous": ("طرابلس", "Tripoli", "Tripoli"), "zahleh": ("زحلة", "Zahlé", "Zahle"),
               "zahlé": ("زحلة", "Zahlé", "Zahle"), "saida": ("صيدا", "Saïda", "Saida"),
               "nabatiyeh": ("النبطية", "Nabatieh", "Nabatieh")}


def _readable_names(communes, osm_ar, place_ar, usage=None):
    """OCHA's names as a reader expects them: with the article OSM gives the same place ("مختارة"
    -> "المختارة"), without the district OCHA appends ("روميه المتن" -> "روميه"; a name shared by
    two districts gets it back in brackets in _disambiguate), and never a bare prefix ("Kafr")."""
    for cand in (osm_ar, place_ar):
        fuller = [c if isinstance(c, str) and has_arabic(c) and _key(c) == _key(a) and c.count("ال") > a.count("ال")
                  else None for c, a in zip(cand, communes.name_ar)]
        communes["name_ar"] = pd.Series(fuller, index=communes.index).fillna(communes.name_ar)
    def strip(name, d):
        """name without a trailing district d, unless what is left is a bare prefix ("راس بعلبك",
        "Mazraat el-Chouf" are names, not "Ras" or "Mazraat el" in the Baalbek or Chouf district)."""
        if not (isinstance(name, str) and isinstance(d, str)):
            return name
        words, dw = name.split(), d.split()
        if len(words) <= len(dw) or _key(" ".join(words[-len(dw):])) != _key(d):
            return name
        rest = words[:-len(dw)]
        if len(rest) == 1 and (rest[0] in AR_PREFIXES or rest[0].lower() in NAME_PREFIXES) \
                or rest[-1].lower() in LATIN_ARTICLES:
            return name
        return " ".join(rest)
    def strip_latin(name, d, ar):
        """The same for a Latin name, its district spelled any way: "Deir El-Moukhalles Ech-Chouf"
        in the Chouf, "Ramyet Bent Jbayl" in Bent Jbeil; not a word of the Arabic name that sounds
        like the district ("Khallet El Mtain" is خلة المتين, in the Metn)."""
        if not (isinstance(name, str) and isinstance(d, str)):
            return name
        words = name.split()
        n = len(re.sub(r"^(?:El|Al|Ech|Es|Ez|Ed|Er|En|Et|Ej) ", "", d).split())   # OCHA's "El Koura", "El Meten"
        for k in (n + 1, n):   # "Maasser El Chouf": the article goes with the district
            tail = " ".join(words[-k:])
            if len(words) > k and sounds_like(tail, d):
                rest = words[:-k]
                if len(rest) == 1 and rest[0].lower() in NAME_PREFIXES or rest[-1].lower() in LATIN_ARTICLES \
                        or isinstance(ar, str) and any(latin_matches(tail, w) for w in ar.split()):
                    return name
                return " ".join(rest)
        return name
    # One decision per commune, taken on the Arabic name, applied in all three scripts; a Latin name
    # also loses a district its Arabic name never had ("Kefraiya Koura" for "كفريا").
    stripped = pd.Series([strip(n, d) for n, d in zip(communes.name_ar, communes.adm2_ar)], index=communes.index)
    cut = (stripped != communes.name_ar) | pd.Series(
        [isinstance(a, str) and isinstance(d, str) and _key(d) not in _key(a) for a, d in zip(stripped, communes.adm2_ar)],
        index=communes.index)
    communes["name_ar"] = stripped
    for col, tail in (("name_fr", "é"), ("name_en", "eh")):
        names = [strip_latin(n, d, a) for n, d, a in
                 zip(communes.loc[cut, col], communes.loc[cut, "adm2_en"], communes.loc[cut, "name_ar"])]
        # Without its district, a name loses the construct ending: "Ramyet Bent Jbayl" -> "Ramyé".
        communes.loc[cut, col] = [re.sub(r"(?<=\w{3})[ea]t$", tail, n) if isinstance(n, str) and a.endswith(("ة", "ه"))
                                  else n for n, a in zip(names, communes.loc[cut, "name_ar"])]
    if usage:   # one-word names OSM mostly writes with the article: "شياح" -> "الشياح", not "روميه"
        def article(n):
            if not isinstance(n, str) or " " in n or n.startswith("ال"):
                return n
            if n in ALWAYS_ARTICLE:
                return "ال" + n
            return "ال" + n if usage["ال" + n] > usage[n] and usage["ال" + n] >= 2 else n
        communes["name_ar"] = communes.name_ar.map(article)
    bare = communes.name_fr.map(lambda n: isinstance(n, str) and n.lower() in NAME_PREFIXES) & \
        communes.name_ar.map(lambda a: isinstance(a, str) and len(a.split()) >= 2)
    communes.loc[bare, "name_fr"] = communes.loc[bare, "name_ar"].map(lambda a: ar_to_latin(a, "fr"))
    communes.loc[bare, "name_en"] = communes.loc[bare, "name_ar"].map(lambda a: ar_to_latin(a, "en"))


def _consistent_names(communes, place_ar, vouched):
    """One place in all three scripts. A cadaster covers several localities, and OCHA sometimes
    names a different one in each script: cadaster 35353 is "Fnaydeq" in English but "النبي خالد" in
    Arabic, two of its five localities in the CAS list. Latin names no OSM object vouches for, and
    naming another place than the Arabic: the Arabic of the OSM village they belong to ("فنيدق")
    when there is one, else Latin names spelled from OCHA's Arabic ("Souaydiyé", not "Michaa
    Mrajhineh" for "سويدية")."""
    for i in communes.index[~vouched]:
        ar, fr, en = communes.at[i, "name_ar"], communes.at[i, "name_fr"], communes.at[i, "name_en"]
        if not has_arabic(ar) or not isinstance(fr, str) or not isinstance(en, str) \
                or all(latin_matches(x, ar, every=True) and _covers(x, ar) or same_sounds(x, ar) for x in (fr, en)):
            continue
        other = fix_ar(place_ar.get(i))
        if has_arabic(other) and (latin_matches(fr, other, every=True) or latin_matches(en, other, every=True)):
            communes.at[i, "name_ar"] = other
            continue
        new_fr, new_en = _aligned(fr, ar, "fr"), _aligned(en, ar, "en")
        if new_fr and new_en:
            communes.at[i, "name_fr"], communes.at[i, "name_en"] = new_fr, new_en
    for i in communes.index[communes.pid.astype(str).isin(CAS_NAMES)]:
        communes.loc[i, ["name_ar", "name_fr", "name_en"]] = CAS_NAMES[str(communes.at[i, "pid"])]


# Cadasters whose OCHA names do not name one place in all three scripts -- another locality of the
# cadaster, a longer form, a typing slip -- where the borrowed OSM name does not settle it either:
# the names the CAS list of localities gives for the same code
# (wiki.openstreetmap.org/wiki/LebanonPlaceNames), or OSM's village where it has one. Street names
# spell the commune as it is named here ("Route de Kfar Tay", not "Route de Kfar Tay Kesrouane"
# for "طريق دير زرعيا").
CAS_NAMES = {
    "10999": ("وسط بيروت", "Centre-ville de Beyrouth", "Beirut Central District"),   # OCHA: "وسط"; not in the CAS list
    "21361": ("قرطاضة", "Qortada", "Qortada"),                    # CAS and OSM village; OCHA: "قرطادة" / "Qordata"
    "22245": ("مار روكز", "Mar Roukoz", "Mar Roukoz"),           # CAS: Deir Mar Roukoz, and Dahr El Hossein next to it
    "22319": ("مزهر", "Mezher", "Mezher"),                        # OSM village; OCHA: "Menqlet Mezher"
    "22754": ("الشوير", "Choueir", "Choueir"),                    # CAS; "Dhour El Choueir" is another locality, an OSM town
    "23651": ("مزرعة الشوف", "Mazraat El Chouf", "Mazraat Al Shouf"),   # CAS: "مزرعة - الشوف"; OCHA: "مزرعة"
    "25121": ("جونيه", "Jounieh", "Jounieh"),                     # OSM city; OCHA: "Jounie Ghadir"
    "25181": ("خرايب نهر ابراهيم", "Kharayeb Nahr Ibrahim", "Kharayeb Nahr Ibrahim"),   # OCHA: "زاير"
    "25439": ("كفر دبيان", "Kfardebian", "Kfardebian"),           # CAS, OSM village; OCHA: "Mazraet Kfardebiane"
    "25447": ("كفر تيه", "Kfar Tay", "Kfar Tay"),                 # CAS: the only locality; OCHA's Arabic: "دير زرعيا"
    "31166": ("بساتين طرابلس", "Bsatine Trablous", "Bsatine Trablous"),   # CAS; OCHA: "بساتين" / "Trablous jardins"
    "33283": ("كفريا", "Kefraiya", "Kefraiya"),                   # CAS; OCHA: "Mzraat Kefraya"
    "35231": ("تلمعيان", "Tall Meaayan", "Tall Meaayan"),         # CAS: Tall Meaayane, and Tall Kiri next to it
    "35425": ("فسقين وعين أشما", "Fsaqine Oua Ain Achma", "Fsaqine Oua Ain Achma"),   # CAS; OCHA's Latin: "Bsatine"
    "37382": ("روضة", "Raouda", "Raouda"),                        # CAS, OSM village; OCHA: "روضه المنيه" / "Aadoueh"
    "51185": ("مزرعة الرمطانية", "Mazraat Er Remtaniyeh", "Mazraat Er Remtaniyeh"),   # CAS; OCHA's Arabic: "الرمطانية"
    "54114": ("سويدية", "Souaydiyé", "Souaydiyeh"),               # OCHA: "Michaa Mrajhineh"
    "54183": ("وادي العص", "Ouadi El-Aaoss", "Ouadi El-Aaoss"),   # CAS, as OCHA's Latin; OCHA's Arabic: "وادي القصص"
    "61115": ("صيدا", "Saïda", "Saida"),                          # CAS: the old city and 15 other localities of Saida
    "61412": ("مزرعة العيتانية", "Mazraat El Aaitaniyeh", "Mazraat El Aaitaniyeh"),   # CAS; OCHA: "Mazraat El Yahoudiyeh"
    "61419": ("الخرائب", "Kharayeb", "Kharayeb"),                 # CAS; OCHA: "Khayayeb"
    "62179": ("دير قانون العين", "Deïr Qanoun El Aïn", "Deir Qanoun El Ain"),   # CAS; OCHA's Arabic "دير قانون" is two towns
    "62214": ("المجادل", "Mjadel", "Mjadel"),                     # CAS, OSM village; OCHA: "Majdel"
    "62242": ("مزرعة عيا", "Mazraat Aaiyeh", "Mazraat Aaiyeh"),   # CAS; OCHA: "Aaiyeh"
    "62312": ("الناقورة", "Naqoura", "Naqoura"),                  # CAS, OSM village; OCHA: "Borj En-Naqoura"
    "63174": ("بيبه", "Bebeh", "Bebeh"),                          # CAS; OCHA: "Behbeh"
    "63234": ("وادي الليمون", "Ouadi El Laymoun", "Wadi El Laymoun"),   # CAS; OCHA's French: "Quadi"
    "63343": ("مزرعة زغرين", "Mazraat Zighrine", "Mazraat Zighrine"),   # CAS; OCHA's Arabic: "زغرين"
    "71361": ("أنصار", "Ansar", "Ansar"),                         # CAS "إنصار" / Insar; the town is known as Ansar
    "74131": ("مرج الزهور", "Marj El Zhour", "Marj El Zhour"),   # CAS "مرج الزهور - الدنيبة": the first, as OCHA's Latin
    "63378": ("مزرعة داريا", "Mazraat Daraya", "Mazraat Daraya"),       # CAS; OCHA's Arabic: "داريا"
}

# Words of a Latin place name that stay lowercase: articles and function words.
LOWER_WORDS = {"el", "al", "ech", "ach", "ash", "es", "ez", "ed", "er", "en", "et", "ej", "ad", "ar", "as", "at", "az",
               "de", "du", "des", "la", "le", "les", "d'", "l'", "oua", "wa", "ou", "w", "of", "the", "and"}


def _ocha_latin(name):
    """OCHA's Latin names without their typing slips: "Mzaraat Zahleh", "Mazraat 'Snaiber", "Kfar hay"."""
    if not isinstance(name, str):
        return name
    name = re.sub(r"(?<=\s)'(?=\w)", "", re.sub(r"\bMza?raat\b", "Mazraat", name))
    first, *rest = name.split(" ")
    return " ".join([first] + [w[:1].upper() + w[1:] if w[:1].islower() and w.split("-")[0].lower() not in LOWER_WORDS
                               else w for w in rest])


def _covers(latin, ar):
    """Every word of the Arabic name has a Latin word that sounds like it ("Hadath" does not cover
    "حدت الهرمل")."""
    tokens = [t.strip(",;()") for t in latin.split()]
    return all(any(latin_matches(t, w) for t in tokens) for w in ar.split() if w != "و")


def _aligned(latin, ar, lang):
    """A Latin name rebuilt on the Arabic one, word by word: each Arabic word keeps the Latin word
    that sounds like it, and any other is spelled from the dictionaries ("Mazraat En-Nahriyeh" for
    "النهريه" -> "En-Nahriyeh"; "Haouch El-Aamara" for "تل العمارة" -> "Tell El-Aamara"). None when a
    word would have to be spelled letter by letter: the name is then left as it is."""
    tokens, out, hits = [t.strip(",;()") for t in latin.split() if t.strip(",;()")], [], 0
    for w in ar.split():
        hit = next((t for t in tokens if latin_matches(t, w)), None)
        if hit:
            tokens.remove(hit)
            out.append(hit)
            hits += 1
            continue
        report = []
        out.append(ar_to_latin(w, lang, report))
        if report:
            out = None
            break
    if not hits:   # another place altogether: the Arabic as the dictionaries spell it ("مدينة الصناعية")
        report = []
        whole = ar_to_latin(ar, lang, report)
        out = None if report else [whole]
    if out is None:
        return None
    name = " ".join(out)
    if ar.endswith(("ة", "ه")):   # "Nasriyet Zahleh" for "ناصرية": "Nasriyé" alone
        name = re.sub(r"(?<=\w{3})[ea]t$", "é" if lang == "fr" else "eh", name)
    return name[:1].upper() + name[1:]


def _towns(communes):
    """town_ar/fr/en: the place a road "leads to" -- the city for a city's cadastral pieces."""
    group = communes.ocha_en.fillna(communes.name_fr).map(
        lambda n: CITY_GROUPS.get(n.split()[0].lower()) if isinstance(n, str) and n.strip() else None)
    for i, lang in enumerate(("ar", "fr", "en")):
        # Without the district in brackets: a street is "Route d'El Khraibé", the commune keeps "(Chouf)".
        communes[f"town_{lang}"] = [g[i] if g else re.sub(r"\s*\([^)]*\)$", "", n)
                                    for g, n in zip(group, communes[f"name_{lang}"])]


DISTRICT_PREFIX = re.compile(r"^(District|Caza|Gouvernorat|قضاء|محافظة)\s+(de la |de l'|du |des |de |d')?", re.I)
DISTRICT_SUFFIX = re.compile(r"\s+(District|Governorate)$", re.I)


def _display_key(name):
    """Two names a reader would confuse: same letters, ignoring case, accents, spacing, punctuation."""
    s = re.sub(r"[ً-ْـ]", "", strip_accents(str(name).lower()))
    s = s.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"}))
    return re.sub(r"[^\w]|_", "", s)


def _disambiguate(communes):
    """A village name used by several communes (Niha in the Chouf and in Zahlé) gets its district
    in brackets; two of the same name in one district (Kfar Sghab in Zgharta) also get north/south
    (or west/east) of each other. A full address is then unique in all of Lebanon."""
    # A name shared in any one language gets its district in all three, so the scripts agree.
    dup = pd.Series(False, index=communes.index)
    for lang in ("ar", "fr", "en"):
        dup |= communes[f"name_{lang}"].map(_display_key).duplicated(keep=False)
    for lang in ("ar", "fr", "en"):
        col = f"name_{lang}"
        short = communes[f"district_{lang}"].map(lambda d: DISTRICT_SUFFIX.sub("", DISTRICT_PREFIX.sub("", d)).strip())
        communes.loc[dup, col] = communes.loc[dup, col] + " (" + short[dup] + ")"
    words = {"ar": ("شمال", "جنوب", "غرب", "شرق"), "fr": ("Nord", "Sud", "Ouest", "Est"),
             "en": ("North", "South", "West", "East")}
    for lang in ("ar", "fr", "en"):
        keys = communes[f"name_{lang}"].map(_display_key)
        for _, grp in communes[keys.duplicated(keep=False)].groupby(keys):
            pts = grp.center
            vertical = (pts.y.max() - pts.y.min()) >= (pts.x.max() - pts.x.min())
            order = (-pts.y if vertical else pts.x).sort_values().index
            for rank, i in enumerate(order):
                for lg in ("ar", "fr", "en"):
                    side = words[lg][(0 if vertical else 2) + rank] if len(order) == 2 else str(rank + 1)
                    name = communes.at[i, f"name_{lg}"]
                    comma = "، " if lg == "ar" else ", "
                    communes.at[i, f"name_{lg}"] = name[:-1] + f"{comma}{side})" if name.endswith(")") else f"{name} ({side})"


def assign(points, communes, quarters):
    """commune_id and quarter_id for each point (GeoSeries in METRIC_CRS)."""
    pts = gpd.GeoDataFrame(geometry=points.values, index=points.index, crs=METRIC_CRS)
    within = gpd.sjoin(pts, communes[["commune_id", "area_km2", "geometry"]], predicate="within")
    within = within.sort_values("area_km2")
    within = within[~within.index.duplicated()]
    commune = within["commune_id"].reindex(pts.index)
    missing = commune.isna()
    if missing.any():
        near = gpd.sjoin_nearest(pts[missing], communes[["commune_id", "geometry"]])
        near = near[~near.index.duplicated()]
        commune.loc[near.index] = near["commune_id"]
    qj = gpd.sjoin(pts, quarters[["quarter_id", "geometry"]], predicate="within")
    qj = qj[~qj.index.duplicated()]
    quarter = qj["quarter_id"].reindex(pts.index)
    return commune, quarter
