"""Arabic <-> Latin conversion for names that exist in only one script.

Lebanese place and landmark names are usually tagged in Arabic, sometimes only in French or
English. When a name needs the missing script, words come from, in order: the reviewed spellings
(spellings.py), the place-name gazetteer, the dictionary below, and the spellings learned from
OSM (lexicon.py). Any other word is transliterated letter by letter (Lebanese French conventions:
ch, j, kh, ou), and the name is flagged for human review.
"""

import re
import unicodedata
from difflib import SequenceMatcher

from .spellings import REVIEWED, REVIEWED_LATIN, SACRED, TRANSCRIBED_LATIN

ARABIC_RE = re.compile(r"[؀-ۿ]")
BIDI_MARKS = re.compile("[‎‏‪-‮⁦-⁩]")   # invisible direction marks some OSM names carry
INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
LATIN_RE = re.compile(r"[A-Za-zÀ-ÿŒœ]")

# Arabic word -> (French, English). Matched on whole words after stripping diacritics.
AR_WORDS = {
    "كنيسة": ("Église", "Church"), "كاتدرائية": ("Cathédrale", "Cathedral"),
    "مسجد": ("Mosquée", "Mosque"), "جامع": ("Mosquée", "Mosque"), "دير": ("Couvent", "Monastery"),
    "مزار": ("Sanctuaire", "Shrine"), "مقام": ("Mausolée", "Shrine"),
    "مدرسة": ("École", "School"), "ثانوية": ("Lycée", "High School"),
    "تكميلية": ("Collège", "Intermediate School"), "متوسطة": ("Collège", "Intermediate School"),
    "ابتدائية": ("Primaire", "Primary"), "رسمية": ("Publique", "Public"), "الرسمية": ("Publique", "Public"),
    "معهد": ("Institut", "Institute"), "جامعة": ("Université", "University"), "كلية": ("Faculté", "Faculty"),
    "مستشفى": ("Hôpital", "Hospital"), "مستوصف": ("Dispensaire", "Dispensary"),
    "بلدية": ("Municipalité", "Municipality"), "سراي": ("Sérail", "Serail"), "السراي": ("Sérail", "Serail"),
    "حديقة": ("Jardin", "Garden"), "منتزه": ("Parc", "Park"), "ملعب": ("Stade", "Stadium"),
    "نبع": ("Source", "Spring"), "ساحة": ("Place", "Square"), "سوق": ("Souk", "Souk"),
    "قلعة": ("Citadelle", "Castle"), "مركز": ("Centre", "Center"), "نادي": ("Club", "Club"),
    "مكتبة": ("Bibliothèque", "Library"), "بريد": ("Poste", "Post"), "مخفر": ("Poste de police", "Police Station"),
    "ثكنة": ("Caserne", "Barracks"), "مقبرة": ("Cimetière", "Cemetery"), "محطة": ("Station", "Station"),
    "مغارة": ("Grotte", "Grotto"), "شاطئ": ("Plage", "Beach"), "تلة": ("Colline", "Hill"),
    "سيدة": ("Notre-Dame", "Our Lady"), "السيدة": ("Notre-Dame", "Our Lady"),
    "القديس": ("Saint", "Saint"), "القديسة": ("Sainte", "Saint"), "مار": ("Mar", "Mar"),
    "الإمام": ("Imam", "Imam"), "الامام": ("Imam", "Imam"), "الشهيد": ("Chahid", "Martyr"),
    "الشيخ": ("Cheikh", "Sheikh"), "الرئيس": ("Président", "President"),
    "راهبات": ("Sœurs", "Sisters"), "الرهبان": ("Pères", "Fathers"), "الفرير": ("Frères", "Brothers"),
    "الموارنة": ("Maronite", "Maronite"), "المارونية": ("Maronite", "Maronite"),
    "الأرثوذكس": ("Orthodoxe", "Orthodox"), "الارثوذكس": ("Orthodoxe", "Orthodox"),
    "الكاثوليك": ("Catholique", "Catholic"), "الأرمن": ("Arménienne", "Armenian"),
    "الإنجيلية": ("Évangélique", "Evangelical"), "السريان": ("Syriaque", "Syriac"),
    "اليسوعية": ("Jésuite", "Jesuit"), "الأنطونية": ("Antonine", "Antonine"),
    "القديم": ("Ancien", "Old"), "القديمة": ("Ancienne", "Old"), "الجديد": ("Nouveau", "New"),
    "الكبير": ("Grand", "Great"), "الكبرى": ("Grande", "Great"),
    "الياس": ("Elias", "Elias"), "جرجس": ("Gerges", "Gerges"), "ميخائيل": ("Mikhael", "Mikhael"),
    "مخايل": ("Mkhayel", "Mkhayel"), "يوحنا": ("Youhanna", "Youhanna"), "بطرس": ("Boutros", "Boutros"),
    "انطونيوس": ("Antonios", "Antonios"), "أنطونيوس": ("Antonios", "Antonios"), "شربل": ("Charbel", "Charbel"),
    "مارون": ("Maroun", "Maroun"), "تقلا": ("Takla", "Takla"), "نهرا": ("Nohra", "Nohra"),
    "ضومط": ("Doumit", "Doumit"), "ساسين": ("Sassine", "Sassine"), "روكز": ("Roukoz", "Roukoz"),
    "عبدا": ("Abda", "Abda"), "شعيا": ("Chaaya", "Chaaya"), "سمعان": ("Semaan", "Semaan"),
    "يعقوب": ("Yaacoub", "Yaacoub"), "طانيوس": ("Tanios", "Tanios"), "موسى": ("Moussa", "Moussa"),
    "يوسف": ("Youssef", "Youssef"), "نقولا": ("Nicolas", "Nicholas"), "سركيس": ("Sarkis", "Sarkis"),
    "ضاهر": ("Daher", "Daher"), "علي": ("Ali", "Ali"), "حسن": ("Hassan", "Hassan"),
    "حسين": ("Hussein", "Hussein"), "محمد": ("Mohammad", "Mohammad"), "عمر": ("Omar", "Omar"),
    "العمري": ("Al-Omari", "Al-Omari"), "المهدي": ("Al-Mahdi", "Al-Mahdi"),
    # Words that recur in Lebanese place names.
    "عين": ("Aïn", "Ain"), "كفر": ("Kfar", "Kfar"), "بيت": ("Beit", "Beit"), "جبل": ("Jabal", "Jabal"),
    "وادي": ("Wadi", "Wadi"), "نهر": ("Nahr", "Nahr"), "حارة": ("Haret", "Haret"), "حي": ("Hay", "Hay"),
    "مزرعة": ("Mazraat", "Mazraat"), "ضهر": ("Dahr", "Dahr"), "رأس": ("Ras", "Ras"), "راس": ("Ras", "Ras"),
    "برج": ("Bourj", "Burj"), "تل": ("Tell", "Tell"), "قرنة": ("Qornet", "Qornet"), "بير": ("Bir", "Bir"),
    "بئر": ("Bir", "Bir"), "جسر": ("Pont", "Bridge"), "عيون": ("Aayoun", "Aayoun"), "مشاع": ("Mchaa", "Mchaa"),
    # Common first names, in the usual Lebanese spelling.
    "جورج": ("Georges", "George"), "ميشال": ("Michel", "Michel"), "بيار": ("Pierre", "Pierre"),
    "شارل": ("Charles", "Charles"), "فؤاد": ("Fouad", "Fouad"), "كميل": ("Camille", "Camille"),
    "بشارة": ("Béchara", "Bechara"), "رفيق": ("Rafic", "Rafic"), "رياض": ("Riad", "Riad"), "سليم": ("Salim", "Salim"),
    "نجيب": ("Najib", "Najib"), "أمين": ("Amine", "Amine"), "امين": ("Amine", "Amine"), "انطوان": ("Antoine", "Antoine"),
    "أنطوان": ("Antoine", "Antoine"), "جوزيف": ("Joseph", "Joseph"), "حنا": ("Hanna", "Hanna"), "طوني": ("Tony", "Tony"),
    "إميل": ("Émile", "Emile"), "اميل": ("Émile", "Emile"), "خليل": ("Khalil", "Khalil"), "جبران": ("Gebran", "Gibran"),
    "كمال": ("Kamal", "Kamal"), "مصطفى": ("Moustafa", "Mustafa"), "عبدالله": ("Abdallah", "Abdallah"),
    "جابر": ("Jaber", "Jaber"), "ابراهيم": ("Ibrahim", "Ibrahim"), "إبراهيم": ("Ibrahim", "Ibrahim"),
    "سمير": ("Samir", "Samir"), "عادل": ("Adel", "Adel"), "فادي": ("Fadi", "Fadi"), "نبيه": ("Nabih", "Nabih"),
    "وليد": ("Walid", "Walid"), "كريم": ("Karim", "Karim"), "خالد": ("Khaled", "Khaled"), "سعد": ("Saad", "Saad"),
    "سعيد": ("Saïd", "Said"), "صالح": ("Saleh", "Saleh"), "رشيد": ("Rachid", "Rashid"), "منير": ("Mounir", "Munir"),
    "نديم": ("Nadim", "Nadim"), "شفيق": ("Chafic", "Shafik"), "توفيق": ("Toufic", "Toufic"), "فارس": ("Farès", "Fares"),
    "حبيب": ("Habib", "Habib"), "داود": ("Daoud", "Daoud"), "بولس": ("Boulos", "Paul"), "فرنسيس": ("François", "Francis"),
    "ماري": ("Marie", "Mary"), "تريز": ("Thérèse", "Theresa"), "رفقا": ("Rafqa", "Rafqa"), "صوما": ("Sawma", "Sawma"),
    "الرئيسي": ("Principale", "Main"), "الرئيسية": ("Principale", "Main"), "عبد": ("Abd", "Abd"), "أبو": ("Abou", "Abou"),
    "ابو": ("Abou", "Abou"), "الدكتور": ("Docteur", "Doctor"), "أحمد": ("Ahmad", "Ahmad"), "احمد": ("Ahmad", "Ahmad"),
    "طريق": ("Route", "Road"), "شارع": ("Rue", "Street"), "زنقة": ("Zanket", "Zanket"), "طلعة": ("Taleet", "Taleet"),
    "طلعت": ("Taleet", "Taleet"), "النبي": ("Nabi", "Nabi"), "نبي": ("Nabi", "Nabi"), "ضهور": ("Dhour", "Dhour"),
    "معمل": ("Usine", "Factory"), "السكر": ("du Sucre", "Sugar"), "المحافظ": ("Mohafez", "Governor"), "الدين": ("ed-Dine", "ed-Din"),
    "سوريا": ("Syrie", "Syria"), "مجد": ("Majd", "Majd"), "السريع": ("Express", "Express"), "عام": ("Principale", "Main"),
    "العام": ("Principale", "Main"), "الحاج": ("el-Hajj", "el-Hajj"), "الحج": ("el-Hajj", "el-Hajj"), "عدنان": ("Adnan", "Adnan"),
    "المنلا": ("el-Mounla", "el-Mounla"), "العريض": ("el-Aarid", "el-Aarid"), "ديميتري": ("Dimitri", "Dimitri"),
    "الحايك": ("el-Hayek", "el-Hayek"), "في": ("à", "in"), "العربي": ("el-Arabi", "el-Arabi"), "كرم": ("Karm", "Karm"),
    "عباس": ("Abbas", "Abbas"), "فريد": ("Farid", "Farid"), "طراد": ("Trad", "Trad"), "وديع": ("Wadih", "Wadih"),
    "نعيم": ("Naïm", "Naim"), "العزيز": ("el-Aziz", "el-Aziz"), "الأزهر": ("el-Azhar", "el-Azhar"), "العقبة": ("el-Aqaba", "el-Aqaba"),
    "الغرب": ("el-Gharb", "el-Gharb"), "شمعون": ("Chamoun", "Chamoun"), "المر": ("el-Murr", "el-Murr"), "شحرور": ("Chahrour", "Chahrour"),
    "غاريوس": ("Gharios", "Gharios"), "جان": ("Jean", "Jean"), "لويس": ("Louis", "Louis"), "أنطون": ("Antoun", "Antoun"),
    "بن": ("Ben", "Bin"), "ابن": ("Ibn", "Ibn"), "الحريري": ("Hariri", "Hariri"), "البحر": ("de la Mer", "Sea"),
    "الحميد": ("el-Hamid", "el-Hamid"), "الجبانة": ("Cimetière", "Cemetery"), "الكاردينال": ("Cardinal", "Cardinal"),
    "فوزي": ("Faouzi", "Fawzi"), "فتال": ("Fattal", "Fattal"), "محي": ("Mohi", "Mohi"), "الرفاعي": ("el-Rifaï", "el-Rifai"),
    "قاسم": ("Kassem", "Qassem"), "مراد": ("Mourad", "Murad"), "الارز": ("des Cèdres", "Cedar"), "أرز": ("Cèdres", "Cedar"),
    "ارز": ("Cèdres", "Cedar"), "الصلح": ("es-Solh", "as-Solh"), "الجميل": ("Gemayel", "Gemayel"), "النعمان": ("Naamane", "Naaman"),
    "مرعي": ("Maraï", "Marai"), "الأثير": ("el-Athir", "al-Athir"), "الشماع": ("Chammaa", "Shammaa"), "حسين": ("Hussein", "Hussein"),
    "محمود": ("Mahmoud", "Mahmoud"), "رامي": ("Rami", "Rami"), "طارق": ("Tarek", "Tarek"), "زياد": ("Ziad", "Ziad"),
    "جميل": ("Jamil", "Jamil"), "نجيب": ("Najib", "Najib"), "حداد": ("Haddad", "Haddad"), "الخوري": ("el-Khoury", "el-Khoury"),
    "غصن": ("Ghosn", "Ghosn"), "مخول": ("Makhoul", "Makhoul"), "نصر": ("Nasr", "Nasr"), "سلامة": ("Salameh", "Salameh"),
    "عيسى": ("Issa", "Issa"), "منصور": ("Mansour", "Mansour"), "شاهين": ("Chahine", "Shahine"), "يونس": ("Younes", "Younes"),
    "الأمير": ("Émir", "Emir"), "الامير": ("Émir", "Emir"), "المطران": ("Mgr", "Bishop"), "الأب": ("Père", "Father"),
    "البطريرك": ("Patriarche", "Patriarch"), "الشيخة": ("Cheikha", "Sheikha"), "الست": ("Sitt", "Sitt"),
    "الحسيني": ("el-Husseini", "al-Husseini"), "الزين": ("ez-Zein", "az-Zein"), "خوري": ("Khoury", "Khoury"),
}

# Latin word (lowercase, accents stripped) -> Arabic. English type words that follow the
# proper noun ("Saint Coeur School") are moved to the front, as Arabic puts them first.
LATIN_WORDS = {
    "eglise": "كنيسة", "church": "كنيسة", "cathedrale": "كاتدرائية", "cathedral": "كاتدرائية",
    "chapelle": "كابيلا", "chapel": "كابيلا", "mosquee": "مسجد", "mosque": "مسجد",
    "couvent": "دير", "monastere": "دير", "monastery": "دير", "convent": "دير",
    "ecole": "مدرسة", "school": "مدرسة", "lycee": "ثانوية", "college": "معهد", "institut": "معهد",
    "institute": "معهد", "universite": "جامعة", "university": "جامعة", "faculte": "كلية", "faculty": "كلية",
    "hopital": "مستشفى", "hospital": "مستشفى", "clinique": "عيادة", "dispensaire": "مستوصف",
    "municipalite": "بلدية", "municipality": "بلدية", "mairie": "بلدية", "jardin": "حديقة",
    "garden": "حديقة", "parc": "منتزه", "park": "منتزه", "stade": "ملعب", "stadium": "ملعب",
    "source": "نبع", "spring": "نبع", "place": "ساحة", "square": "ساحة", "souk": "سوق", "market": "سوق",
    "citadelle": "قلعة", "castle": "قلعة", "chateau": "قصر", "centre": "مركز", "center": "مركز",
    "club": "نادي", "bibliotheque": "مكتبة", "library": "مكتبة", "musee": "متحف", "museum": "متحف",
    "notre-dame": "سيدة", "notre": "سيدة", "dame": "", "lady": "سيدة", "our": "",
    "saint": "مار", "sainte": "القديسة", "st": "مار", "ste": "القديسة", "mar": "مار",
    "public": "الرسمية", "publique": "الرسمية", "official": "الرسمية", "officielle": "الرسمية",
    "high": "الثانوية", "secondary": "الثانوية", "of": "", "de": "", "des": "", "du": "", "la": "",
    "le": "", "les": "", "the": "", "and": "و", "et": "و", "l": "", "d": "",
    "rue": "شارع", "street": "شارع", "route": "طريق", "road": "طريق", "avenue": "جادة", "boulevard": "جادة",
    "impasse": "زاروب", "ruelle": "زاروب", "lane": "زاروب", "autoroute": "أوتوستراد", "highway": "أوتوستراد",
    "autostrad": "أوتوستراد", "corniche": "كورنيش", "principale": "الرئيسية", "main": "الرئيسية",
    "pere": "الأب", "father": "الأب", "emigres": "المهاجرين", "old": "القديم", "ancienne": "القديمة",
    "new": "الجديد", "nouvelle": "الجديدة", "president": "الرئيس", "general": "الجنرال", "cheikh": "الشيخ",
    "sheikh": "الشيخ", "imam": "الإمام", "emir": "الأمير", "mgr": "المطران", "monseigneur": "المطران",
}
EN_TRAILING_TYPES = {"street", "road", "avenue", "lane", "highway", "boulevard", "school", "church", "mosque", "hospital", "university", "park", "garden", "stadium",
                     "museum", "library", "center", "centre", "monastery", "convent", "college", "institute",
                     "municipality", "square", "market", "spring", "chapel", "cathedral", "clinic"}

FR_PLACE_NOUNS = {"Église", "Mosquée", "Couvent", "École", "Lycée", "Collège", "Institut", "Université", "Faculté",
                  "Hôpital", "Dispensaire", "Municipalité", "Jardin", "Parc", "Stade", "Source", "Souk", "Citadelle",
                  "Centre", "Club", "Bibliothèque", "Caserne", "Cimetière", "Station", "Grotte", "Plage", "Sérail"}
EN_TYPE_NOUNS = {
    "Church", "Cathedral", "Mosque", "Monastery", "Shrine", "School", "High School", "Intermediate School",
    "Institute", "University", "Faculty", "Hospital", "Dispensary", "Municipality", "Serail", "Garden", "Park",
    "Stadium", "Spring", "Square", "Souk", "Castle", "Center", "Club", "Library", "Post", "Police Station",
    "Barracks", "Cemetery", "Station", "Grotto", "Beach", "Hill",
}

AR_CHARS = {
    "ا": "a", "أ": "a", "إ": "i", "آ": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h",
    "خ": "kh", "د": "d", "ذ": "z", "ر": "r", "ز": "z", "س": "s", "ش": "ch", "ص": "s", "ض": "d",
    "ط": "t", "ظ": "z", "ع": "a", "غ": "gh", "ف": "f", "ق": "k", "ك": "k", "ل": "l", "م": "m",
    "ن": "n", "ه": "h", "و": "ou", "ي": "i", "ى": "a", "ة": "é", "ء": "", "ئ": "i", "ؤ": "ou",
}
LATIN_VOWELS = set("aeiouy")
LATIN_DIGRAPHS = [("ch", "ش"), ("sh", "ش"), ("kh", "خ"), ("gh", "غ"), ("th", "ث"), ("ou", "و"),
                  ("oo", "و"), ("ee", "ي"), ("ai", "اي"), ("ay", "اي"), ("ei", "ي"), ("ey", "ي"),
                  ("ph", "ف"), ("qu", "ك"), ("aa", "ا")]
LATIN_CHARS = {
    "a": "ا", "e": "", "i": "ي", "o": "و", "u": "و", "y": "ي", "b": "ب", "c": "ك", "d": "د",
    "f": "ف", "g": "غ", "h": "ه", "j": "ج", "k": "ك", "l": "ل", "m": "م", "n": "ن", "p": "ب",
    "q": "ق", "r": "ر", "s": "س", "t": "ت", "v": "ف", "w": "و", "x": "كس", "z": "ز",
}


def has_arabic(text):
    return isinstance(text, str) and bool(ARABIC_RE.search(text))


def has_latin(text):
    return isinstance(text, str) and bool(LATIN_RE.search(text))


def strip_accents(text):
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _ar_word_to_latin(word):
    prefix = ""
    if word.startswith("ال") and len(word) > 3:
        prefix, word = "el-", word[2:]
    out = "".join(AR_CHARS.get(c, "") for c in word)
    # Arabic omits short vowels; break a leading consonant cluster so the word is pronounceable.
    if len(out) > 2 and out[0] not in LATIN_VOWELS and out[1] not in LATIN_VOWELS and out[:2] not in ("ch", "kh", "gh", "th"):
        out = out[0] + "a" + out[1:]
    return prefix + out.capitalize()


# Known place names, Arabic -> (French, English) and Latin -> Arabic, registered by the pipeline
# from OSM communes and places so "مدرسة بكفيا" becomes "École Bikfaya", not "École Bakfia".
GAZETTEER_AR, GAZETTEER_LATIN = {}, {}


def _ar_key(text):
    s = re.sub(r"[ً-ْـ]", "", text.strip())
    return s.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"}))


def _latin_key(text):
    """'Minet el-Hosn' and 'Minet El Hosn' are the same place."""
    return re.sub(r"[\s\-'’]+", " ", strip_accents(text.lower())).strip()


REVIEWED_AR = {_ar_key(k): v for k, v in REVIEWED.items()}
SACRED_AR = {_ar_key(k) for k in SACRED}


def register_gazetteer(rows):
    """rows: iterable of (arabic, french, english)."""
    for ar, fr, en in rows:
        if has_arabic(ar) and isinstance(fr, str) and isinstance(en, str) and len(ar.split()) <= 3:
            GAZETTEER_AR.setdefault(_ar_key(ar), (modern_spelling(fr), modern_spelling(en)))
            GAZETTEER_LATIN.setdefault(_latin_key(fr), ar)
            GAZETTEER_LATIN.setdefault(_latin_key(en), ar)


# Spellings learned from OSM objects named in both scripts (see lexicon.py), registered by the
# pipeline: Arabic word -> French / English, and Latin word -> Arabic.
LEXICON = {"fr": {}, "en": {}, "ar": {}}


def lex_ar_key(word):
    w = re.sub(r"[\u064B-\u0652\u0640\u0670]", "", word)
    return w.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي"}))


def lex_lat_key(word):
    return strip_accents(word.lower()).strip(".,()'’")


def register_lexicon(lexicon):
    for k in LEXICON:
        LEXICON[k].update(lexicon.get(k, {}))


def _match_place(words, i, gazetteer, key, longest=3):
    """Longest run of up to `longest` words starting at i that is a known place name, with or
    without the Arabic article ("الحجير" matches "حجير")."""
    for n in range(longest, 0, -1):
        if i + n <= len(words):
            phrase = " ".join(words[i:i + n])
            variants = [phrase]
            if has_arabic(phrase):
                variants.append(phrase[2:] if phrase.startswith("ال") else "ال" + phrase)
            for v in variants:
                hit = gazetteer.get(key(v))
                if hit is not None:
                    return hit, n
    return None, 0


# The themed street names, read the other way: OSM's "شارع الغار" is "Rue des Lauriers" / "Laurel
# Street", as a themed street would be. Concrete nouns only: "السلام" and "النور" also end first
# names ("عبد السلام"), and no theme word is read right after عبد, أبو or ابن.
THEME_AR = {}
NAME_LINKS = {"عبد", "ابو", "أبو", "ابن", "إبن", "بن", "بنت", "ام", "أم"}
# Names spelled with a hamza on the alef, matched exactly: every other lookup reads "أل" as the
# article "ال".
HAMZA_NAMES = {"ألفريد": ("Alfred", "Alfred"), "ألفرد": ("Alfred", "Alfred"), "ألبير": ("Albert", "Albert"),
               "ألبرت": ("Albert", "Albert"), "ألكساندر": ("Alexandre", "Alexander"),
               "ألكسندر": ("Alexandre", "Alexander")}


def _theme_arabic():
    from .themes import THEMES
    for cat in ("trees", "flowers", "birds", "gems", "animals"):
        for ar, fr, en in THEMES[cat]:
            THEME_AR.setdefault(_ar_key(ar), (fr, en))
    for entries in THEMES.values():   # "Rue des Lauriers" with no English tag is "Laurel Street"
        for ar, fr, en in entries:
            noun = re.sub(r"^(des|du|de la|de l'|de)\s*", "", fr)
            if " " not in noun and noun != en:
                FR_EN_WORDS.setdefault(noun, en)
            FR_CIRCUMFLEX.update(w.lower() for w in re.findall(r"\w+", fr) if re.search("[âîû]", w))


def _theme_at(words, i):
    if i and words[i - 1] in NAME_LINKS:
        return None, 0
    for n in (3, 2, 1):
        hit = THEME_AR.get(_ar_key(" ".join(words[i:i + n]))) if i + n <= len(words) else None
        if hit:
            return hit, n
    return None, 0


def _ar_word(word, lang):
    """One Arabic word from the reviewed spellings, the dictionary or the learned lexicon; None
    if none of them knows it."""
    idx = 0 if lang == "fr" else 1
    if word in HAMZA_NAMES:
        return HAMZA_NAMES[word][idx]
    reviewed = REVIEWED_AR.get(_ar_key(word))
    if reviewed:
        return reviewed[idx]
    norm_key = lex_ar_key(word).replace("ة", "ه")
    if word in AR_WORDS:
        return AR_WORDS[word][idx]
    if word.startswith("ال") and word[2:] in AR_WORDS:
        return AR_WORDS[word[2:]][idx]
    # Only a bare "ال" is the article: "ألفريد" is Alfred, not al-Farid, and "ألبير" Albert, not the
    # lexicon's "البير" (the well).
    if norm_key in AR_WORDS_NORM or (word.startswith("ال") and norm_key[2:] in AR_WORDS_NORM):
        return (AR_WORDS_NORM.get(norm_key) or AR_WORDS_NORM[norm_key[2:]])[idx]
    k = lex_ar_key(word)
    hit = LEXICON[lang].get(k) or LEXICON["fr"].get(k)
    if hit and word.startswith("أل") and re.match(r"(?i)(el|al|ech|ach|es|ez|ed|er|en|et|ej)[- ]", hit):
        return None   # learned from "البير" (the well, "el-Bîr"); "ألبير" is a name ("ألياس" is Elias)
    return hit


AR_PLACE_PREFIX = {"حي", "حارة", "عين", "كفر", "بيت", "دير", "ضهر", "رأس", "راس", "برج", "تل", "وادي", "مزرعة"}
PLACE_ADJ = {_ar_key(k): v for k, v in {
    "الجديد": ("el-Jdid", "al-Jdid"), "الجديدة": ("el-Jdidé", "al-Jdideh"), "القديم": ("el-Qadim", "al-Qadim"),
    "القديمة": ("el-Qadimé", "al-Qadimeh"), "الكبير": ("el-Kbir", "al-Kbir"), "الكبيرة": ("el-Kbiré", "al-Kbireh"),
    "الفوقا": ("el-Faouqa", "al-Fawqa"), "التحتا": ("et-Tahta", "at-Tahta"), "الغربي": ("el-Gharbi", "al-Gharbi"),
    "الشرقي": ("ech-Charqi", "ash-Sharqi"), "الشمالي": ("ech-Chmali", "ash-Shamali"),
    "الجنوبي": ("ej-Jnoubi", "al-Janoubi")}.items()}
# French adjectives: (masculine, feminine, comes before the noun).
FR_ADJ = {"Grand": ("Grand", "Grande", True), "Grande": ("Grand", "Grande", True), "Nouveau": ("Nouveau", "Nouvelle", True),
          "Nouvelle": ("Nouveau", "Nouvelle", True), "Ancien": ("Ancien", "Ancienne", True),
          "Ancienne": ("Ancien", "Ancienne", True), "Principale": ("principal", "principale", False),
          "Publique": ("public", "publique", False), "Officielle": ("officiel", "officielle", False),
          "Secondaire": ("secondaire", "secondaire", False), "Primaire": ("primaire", "primaire", False),
          "Mixte": ("mixte", "mixte", False), "Maronite": ("maronite", "maronite", False),
          "Orthodoxe": ("orthodoxe", "orthodoxe", False), "Catholique": ("catholique", "catholique", False),
          "Arménienne": ("arménien", "arménienne", False), "Évangélique": ("évangélique", "évangélique", False)}


def _fr_adjectives(words):
    """Adjectives of a landmark noun in French order and gender: ["Mosquée", "d'Aydamoun", "Grand"]
    -> ["Grande", "Mosquée", "d'Aydamoun"]."""
    feminine = strip_accents(words[0].lower()) in FR_FEMININE
    pre, post, rest = [], [], []
    for w in words[1:]:
        a = FR_ADJ.get(w)
        if a:
            (pre if a[2] else post).append(a[1] if feminine else a[0])
        else:
            rest.append(w)
    return pre + [words[0]] + post + rest


def _from_lexicon(word):
    k = lex_ar_key(word)
    return k not in AR_WORDS and lex_ar_key(word).replace("ة", "ه") not in AR_WORDS_NORM \
        and _ar_key(word) not in REVIEWED_AR and (k in LEXICON["fr"] or k in LEXICON["en"])


def ar_to_latin(text, lang="fr", report=None, sources=None):
    """Arabic name -> French- or English-leaning Latin name. Appends to `report` when some word had
    to be spelled letter by letter (not found in the dictionary or the place-name gazetteer), and to
    `sources` where each word came from: reviewed, gazetteer, dictionary, lexicon or letters."""
    src = sources if sources is not None else []
    idx = 0 if lang == "fr" else 1
    words, places_at = [], set()
    raw = [w.strip("()،,.") for w in re.sub(r"[ً-ْـ]", "", text).replace("-", " - ").split()]
    raw = [w for w in raw if w]
    i = 0
    while i < len(raw):
        reviewed, n = _match_place(raw, i, REVIEWED_AR, _ar_key, longest=5)
        place, m = _match_place(raw, i, GAZETTEER_AR, _ar_key)
        if reviewed and n >= m:
            words.append(reviewed[idx])
            src.append("dictionary" if _ar_key(" ".join(raw[i:i + n])) in SACRED_AR else "reviewed")
            i += n
            continue
        if place and not (m == 1 and raw[i] in AR_WORDS):
            places_at.add(len(words))
            words.append(place[idx])
            src.append("gazetteer")
            i += m
            continue
        theme, t = _theme_at(raw, i)
        if theme:
            words.append(theme[idx])
            src.append("dictionary")
            i += t
            continue
        bare = raw[i]
        i += 1
        if bare == "-":
            words.append("-")
            continue
        known = _ar_word(bare, lang)
        if i >= 2 and raw[i - 2] in AR_PLACE_PREFIX and _ar_key(bare) in PLACE_ADJ:
            known = PLACE_ADJ[_ar_key(bare)][idx]
        if known is None and bare.startswith("و") and len(bare) > 3 and _ar_word(bare[1:], lang):
            known = ("et " if lang == "fr" else "and ") + _ar_word(bare[1:], lang)   # "وبولس": "et Paul"
        if known is not None:
            words.append(known)
            src.append("lexicon" if _from_lexicon(bare) else "dictionary")
        elif bare.translate(INDIC_DIGITS).isdigit():
            words.append(bare.translate(INDIC_DIGITS))
            src.append("dictionary")
        elif has_arabic(bare):
            words.append(_ar_word_to_latin(bare))
            src.append("letters")
            if report is not None:
                report.append(bare)
        else:
            words.append(bare)
            src.append("dictionary")
    if lang == "fr" and len(words) > 1 and words[0] in FR_PLACE_NOUNS and 1 in places_at:
        words[1] = fr_route_to(words[1])   # "Municipalité de Debbiyé", "École de Rmeich"
    if lang == "fr" and words and words[0] in FR_PLACE_NOUNS:
        words = _fr_adjectives(words)      # "Grande Mosquée d'Aydamoun", "École publique de Baakline"
    if words in (["Mgr"], ["Bishop"]):     # "شارع المطران" alone: the bishop's street
        words = ["el-Matrane" if lang == "fr" else "al-Matran"]
    words = [w for w in words if w]
    if lang == "en":   # "سيدة الملائكة" not reviewed: "Our Lady of Angels", not "Our Lady Angels"
        words = [w + " of" if w == "Our Lady" and k + 1 < len(words) and words[k + 1] not in EN_TYPE_NOUNS
                 and not words[k + 1].isdigit() else w for k, w in enumerate(words)]
    # English puts the type noun last: "Mar Elias Church", not "Church Mar Elias" -- unless a
    # preposition follows it: "Church in the Rock".
    if lang == "en" and len(words) > 1 and words[0] in EN_TYPE_NOUNS and not words[1].isdigit() \
            and words[1].split()[0].lower() not in ("in", "of", "at", "on", "by"):
        words = words[1:] + words[:1]
    return modern_spelling(" ".join(words))


def _latin_word_to_ar(word):
    """Letter-level spelling of a French-style Lebanese romanization: doubled letters are one
    Arabic letter, "aa" marks an ayn ("Aaba" عابا, "Chaaya" شعيا), "ii" is "عي" ("Rafii" رافعي),
    and a final -ah/-eh/-é is a ta marbuta."""
    raw = word.lower()
    tail = ""
    if len(raw) > 3 and (raw.endswith(("ah", "eh")) or raw.endswith("é")):
        raw, tail = (raw[:-2] if raw.endswith(("ah", "eh")) else raw[:-1]), "ة"
    w = strip_accents(raw)
    w = re.sub(r"^aa", "\x01", w)                 # initial ayn + alef
    w = w.replace("aa", "\x02").replace("ii", "\x03")
    w = re.sub(r"([bcdfghjklmnpqrstvwxz])\1", r"\1", w)
    out, i = [], 0
    while i < len(w):
        c = w[i]
        if c in "\x01\x02\x03":
            out.append({"\x01": "عا", "\x02": "ع", "\x03": "عي"}[c])
            i += 1
            continue
        pair = w[i:i + 2]
        hit = next((ar for lat, ar in LATIN_DIGRAPHS if pair == lat), None)
        if hit is not None:
            out.append(hit)
            i += 2
            continue
        if i == 0 and c in LATIN_VOWELS:
            out.append("إ" if c in "ie" else "أ")
        elif c == "e" and i == len(w) - 1 and len(w) > 2:
            out.append("ه")
        else:
            out.append(LATIN_CHARS.get(c, ""))
        i += 1
    return "".join(out) + tail


LATIN_ARTICLES = {"al", "el", "ad", "ed", "aj", "ej", "es", "ash", "ech", "az", "ez", "ar", "er",
                  "ei"}   # not "et", "en", "at": French and English words; "ei": OSM typo for "el"
# Latin letters inside an Arabic name are written the way Arabic writes them: acronyms by their
# letter names ("WBCC" -> "دبليو بي سي سي"), a person's initials as Arabic initials ("J. P. كرم" ->
# "ج. ب. كرم"), pronounceable acronyms and other words by their sound ("FIFA" -> "فيفا").
LETTER_NAMES = dict(A="إيه", B="بي", C="سي", D="دي", E="إي", F="إف", G="جي", H="إتش", I="آي", J="جيه", K="كيه",
                    L="إل", M="إم", N="إن", O="أو", P="بي", Q="كيو", R="آر", S="إس", T="تي", U="يو", V="في",
                    W="دبليو", X="إكس", Y="واي", Z="زد")
INITIALS = dict(A="أ", B="ب", C="ك", D="د", E="إ", F="ف", G="ج", H="هـ", I="إ", J="ج", K="ك", L="ل", M="م", N="ن",
                O="أ", P="ب", Q="ق", R="ر", S="س", T="ت", U="أ", V="ف", W="و", X="كس", Y="ي", Z="ز")
ROMAN = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6", "VII": "7", "VIII": "8", "IX": "9"}


def _pronounceable(letters):
    low = letters.lower()
    return len(low) >= 4 and re.search(r"[aeiouy]", low) and not re.search(r"[^aeiouy]{3}", low) \
        and not re.match(r"[aeiouy]{2}", low)


def spell_latin_in_arabic(text):
    """Arabic name with Latin letters left in it -> all Arabic script (see LETTER_NAMES)."""
    if not isinstance(text, str) or not LATIN_RE.search(text):   # also an Arabic name that is only "WBCC"
        return text
    tokens = text.split(" ")
    out = []
    for k, tok in enumerate(tokens):
        if not LATIN_RE.search(tok) or has_arabic(tok):
            out.append(tok)
            continue
        letters = re.sub(r"[^A-Za-z]", "", strip_accents(tok))
        digits = re.sub(r"[^0-9]", "", tok)
        after = tokens[k + 1] if k + 1 < len(tokens) else ""
        initial_next = has_arabic(after) or bool(re.fullmatch(r"[A-Za-z]\.", after))
        if k and tok in ROMAN and not initial_next:
            word = ROMAN[tok]                                            # "شارع نيارب I" -> "شارع نيارب 1"
        elif re.fullmatch(r"[A-Za-z]\.", tok) or (re.fullmatch(r"[A-Za-z]", tok) and initial_next):
            word = INITIALS[letters.upper()] + "."                       # "J. P. كرم", "S زيتليان"
        elif _pronounceable(letters):
            word = _latin_word_to_ar(letters)                            # "FIFA", "ADEX"
        elif len(letters) <= 5:
            word = " ".join(LETTER_NAMES[c] for c in letters.upper())     # "WBCC", "F.R.A.", "H"
        else:
            word = _latin_word_to_ar(letters)
        out.append(f"{word} {digits}" if digits else word)
    return " ".join(out)


def split_bilingual(name):
    """'Fadous-فدعوس', 'Lady Stanhope Ruins آثارات لايدي ستانهوب': the same name in both scripts ->
    (arabic, latin); else (None, None). An acronym in an Arabic name ('مدرسة BIS') is not one."""
    if not (isinstance(name, str) and has_arabic(name) and has_latin(name)):
        return None, None
    parts = [p for p in re.split(r"\s*[-/|]\s*|\s+", name) if p]
    ar = " ".join(p for p in parts if has_arabic(p) and not has_latin(p))
    lat = " ".join(p for p in parts if has_latin(p) and not has_arabic(p))
    if ar and lat and any(not w.isupper() for w in re.findall(r"[A-Za-zÀ-ÿ]{4,}", lat)):
        return ar, lat
    return None, None


# Recurring slips in OSM's own names, fixed per language (typos, wrong-language words, odd terms).
FIX_FR = [(r"\bGeneral\b", "Général"), (r"\bPere\b", "Père"), (r"\bMere\b", "Mère"),
          (r"\bS(?:œ|oe)r\b", "Sœur"), (r"\bAutostrade?\b", "Autoroute"), (r"\bRoute [Mm]aritime\b", "Route de la Mer"),
          (r"\bAutoroute [Mm]aritime\b", "Autoroute de la Mer"), (r"\bRue Douanes\b", "Rue des Douanes"),
          (r"\bHarîssa\b", "Harissa"), (r"\bShaïlé\b", "Sehaïlé"), (r"\bKarmel-Zettoun\b", "Karm el-Zeitoun"),
          (r"\bSagese\b", "Sagesse"), (r"\bHyram\b", "Hiram"), (r"\b(?:Jn(?:ou|u)?blat|Jounblat)\b", "Joumblatt"),
          (r"\bTalet Al Central\b", "Talet el-Markazi"), (r"(?<=\S) (De|Du|Des|La|Le|Les)(?= )", lambda m: " " + m.group(1).lower()),
          (r"(?<=\S) De L'", " de l'"), (r"\bCollege\b", "Collège"),
          (r"^Lebanon Mountain Trail Section", "Sentier de Montagne du Liban Section"),
          (r"\bPresident\b", "Président"), (r"\bSaint[- ]Rock\b", "Saint-Roch"), (r"\bElcheikh\b", "Cheikh"),
          (r"\s*\(Po[eè]te\)", ""), (r"\bBusros\b", "Bustros"), (r"\bBranjne\b", "Barajneh"),
          (r"^(?!(?:Rue|Route|Avenue|Impasse|Place|Boulevard|Chemin|Allée|Autoroute|Passage)\b)(.+) (Route|Rue|Place)$",
           r"\2 \1"),   # "Nahleh Route", "Fourzol Place": type first (not "Route de la Place")
          (r"^(Rue|Route|Avenue|Impasse|Place|Boulevard|Passage|Chemin|Allée) (Père|Patriarche|Cheikh|Président|Général|"
           r"Colonel|Docteur|Professeur|Mufti|Commandant|Capitaine|Juge|Cardinal)\b", r"\1 du \2"),
          (r"^(Rue|Route|Avenue|Impasse|Place|Boulevard|Passage|Chemin|Allée) (Émir|Imam|Abbé|Évêque|Archevêque)\b",
           r"\1 de l'\2"),
          (r"^(?:Rue )?Chraa ", "Rue "), (r"\bKamil Chamoun\b", "Camille Chamoun"), (r"\bRue de Sœur\b", "Rue Sœur"),
          (r"\bMarie-Noel\b", "Marie-Noël"), (r"\bCléopatre\b", "Cléopâtre"), (r"\bEamiliyé\b", "Aamiliyé"),
          # "Route Générale de Mqaïblé" (الطريق العام) is a main road, as the other names say it
          (r"^(Route|Rue) [Gg][ée]n[ée]rale (?=de |d'|du )", r"\1 principale "),
          (r"\bde (?=(?:El|Al)\b)", "d'"), (r"\s*&\s*", " et "),
          (r"^(?!(?:Rue|Route|Avenue|Impasse)\b)([A-Z]\w+) (Rue|Route) (\d+)$", r"\2 \1 \3"),   # "Slav Rue 200"
          (r"^(Route|Rue) principale de (.+) Ancienne$", lambda m: f"Ancienne {m.group(1).lower()} principale de {m.group(2)}"),
          (r"\bAchie El Daya\b", "Achir El Daya"), (r"\bVahchouch\b", "Yahchouch"), (r"\bde Dotations\b", "des Wakfs"),
          (r"\bPavillion\b", "Pavillon"), (r"^Route Coastal\b", "Route côtière"), (r"^Autoroute Coastal\b", "Autoroute de la Mer"),
          (r"\b(Jbeil|Jbail) Byblos\b", r"\1"), (r"^(Rue|Route|Avenue) (Immigrants|Émigrés|Emigres|Emigrants|Émigrants)\b",
                                                r"\1 des \2"), (r"\bdes Emigrants\b", "des Émigrants"),
          (r"^Rue R[ée]publique Dominicaine$", "Rue de la République dominicaine"),
          (r"^Rue principale (?:de 2nd|d'Al-Thani)$", "Deuxième Rue principale"),   # "الشارع الرئيسي الثاني"
          (r"^Rue principale de 1st$", "Première Rue principale"), (r"^(Rue|Route) (Lower|Upper) (.+)$",
                                                                    lambda m: f"{m[1]} {m[3]} {'inférieure' if m[2] == 'Lower' else 'supérieure'}"),
          (r"\bElphajj\b", "El Hajj"), (r"\bAtcl\b", "ATCL"), (r"\bSidon\b", "Saïda"), (r"\bBakhistay\b", "Bkhichtay"),
          (r"^(Rue|Route|Avenue) Hôtel[- ]Dieu\b", r"\1 de l'Hôtel-Dieu"), (r"\bDa[iy]r\b", "Deir"),
          (r"\bSaint-Pierre et (?:Boulos|Paul)\b", "Saints-Pierre-et-Paul"), (r"\bMucharafieh\b", "Mcharrafieh"),
          (r"\bd'Hay des Chrétiens\b", "du Quartier chrétien"), (r"\bHay des Chrétiens\b", "Quartier chrétien"),
          (r"\bd'Al Hikmat\b", "de la Sagesse"), (r"\bAl Hikmat\b", "La Sagesse"), (r"\bEl-Khoubra\b", "el-Koubra"),
          (r"^Rue Asfahan\b", "Rue d'Ispahan"), (r"\bAl Hrawi\b", "Hraoui"), (r"\bde Park\b", "du Parc"), (r"\bQuadi\b", "Ouadi"),
          (r"\b[Dd]e L'Advocat\b", "de l'Avocat"), (r"(?<=\w)'s\b", ""), (r"^Rue Arc de\b", "Rue de l'Arc de"),
          (r"^(Rue|Route) (\S+) Principale$", lambda m: f"{m[1]} principale {fr_route_to(m[2])}"), (r"\bMgr\. ", "Mgr "),
          (r"^Rue Al-Barid$", "Rue de la Poste"), (r"\bMitaine\b", "Mitein"),
          (r"^Vieux Souk ([A-Z]\w+)$", r"Vieux Souk de \1"), (r"\bd'Assaraya\b", "de Hay el-Saraya"),
          (r"\bMaisons Priv[ée]e?s?\b", "Maisons privées"), (r"^Avenida Brasil$", "Avenue du Brésil"),
          (r"\bamine gemayel\b", "Amine Gemayel"), (r"\bAlias\b", "Elias"), (r"\bPochkine\b", "Pouchkine"),
          (r"^(Rue|Avenue|Route) Roi\b", r"\1 du Roi"), (r"\bEamiliy[ée]h?\b", "Aamiliyé"),
          (r"^(Rue|Route) (\d+) ((?:(?:Al|El) )?[A-Z][^\s\d]*)$", r"\1 \3 \2"),   # "Rue 107 Al Mountazah": no house number
          (r"\bClémenceau\b", "Clemenceau"), (r"\bJounie\b", "Jounieh"), (r"(?<=\w)- (?=\w)|(?<=\w) -(?=\w)", " - "),
          (r"^Rue Rua\b", "Rue"), (r"\bAbel Alhussein\b", "Abdel Hussein"), (r"\bLake View\b", "Belvédère du Lac"),
          (r"^Rue Ruines Omeyyades\b", "Rue des Ruines omeyyades"), (r"^Route Cèdres - ", "Route des Cèdres - "),
          (r"(?<![Dd]u )\bCompagnon (?=[A-Z])", "du Compagnon "), (r"\bSainte-Hanne\b", "Sainte-Anne"), (r"^Rue Farm$", "Rue de la Ferme"),
          (r"\bCedres\b", "Cèdres"), (r"\bSaint Mitre\b", "Mar Mitr"), (r"\bMont la Salle\b", "Mont La Salle"),
          (r"\bSt-(?=[A-Z])", "Saint-"), (r"^Route El Arz - ", "Route des Cèdres - "), (r"^Route Seaside$", "Route du Bord de mer"),
          (r"\bSaint-Antonios\b", "Saint-Antoine"),
          # A country takes its article: "Rue de Syrie", "Rue du Brésil", "Rue d'Égypte"
          (r"^(Rue|Avenue|Route) (Syrie|Jordanie|Turquie|Russie|Belgique|Suisse|Grèce|Tunisie|Libye|Arménie|Palestine|France|"
           r"Italie|Allemagne|Chine|Inde|Australie)\b", r"\1 de \2"),
          (r"^(Rue|Avenue|Route) (Liban|Mexique|Brésil|Chili|Koweït|Qatar|Japon|Maroc|Soudan|Yémen|Venezuela|Canada|"
           r"Portugal|Danemark|Vatican)\b", r"\1 du \2"),
          (r"^(Rue|Avenue|Route) (Égypte|Irak|Iran|Algérie|Arabie|Argentine|Autriche|Angleterre|Espagne)\b", r"\1 d'\2")]
FIX_EN = [(r"\bS(?:œ|oe)r\b", "Sister"), (r"\bAutostrade?\b", "Highway"),
          (r"\bSea Highway\b", "Coastal Highway"),   # the coastal motorway; a طريق البحر is a "Sea Road" down to the sea
          (r"\bCamile\b", "Camille"), (r"\bHairam\b", "Hiram"), (r"\bSeaSide\b", "Seaside"),
          (r"\bH(?:a)?rissa\b", "Harissa"), (r"\bShaileh\b", "Sehaileh"), (r"\bNassrallah\b", "Nasrallah"),
          (r"\b(?:Jnublat|Janbulat|Jnoublat|Jounblat|Joumblatt)\b", "Jumblatt"), (r"\bKarmel-Zettoun\b", "Karm El Zeitoun"),
          (r"\bMontagne du (?:Liban|Lebanon) Section (\d+) Trail\b", r"Lebanon Mountain Trail Section \1"),
          (r"\bElphajj\b", "El Hajj"), (r"\bAtcl\b", "ATCL"), (r"\bBakhistay\b", "Bkhichtay"), (r"\bRamadane\b", "Ramadan"),
          (r"\bH[ôo]tel[- ]Dieu\b", "Hôtel-Dieu"), (r"\bDa[iy]r\b", "Deir"), (r"\bSaint Peter and Paul\b", "Saints Peter and Paul"),
          (r"\b(?:Christians Neighbourhood|Hay Christians)\b", "Christian Quarter"), (r"\bAl Hikmat\b", "Hikmeh"),
          (r"\b(?:Knights|Chevaliers) du Temple\b", "Knights Templar"), (r"\bAsfahan\b", "Isfahan"), (r"\bAl Hrawi\b", "Hrawi"),
          (r"^As-Souq Al-'?Atiq\b", "Old Souk"), (r"^Sea Express Road$", "Coastal Highway"),
          (r"^Sea (?!Express\b)([A-Z]\S*) Road$", r"\1 Sea Road"),   # "طريق البحر فدعوس": Fadous Sea Road
          (r"^Old Souk (?!(?:Street|Road|Lane|Square|Way|Path)\b)([A-Z]\w+)\b", r"\1 Old Souk"),
          (r"^Assaraya\b", "Hay El Saraya"), (r"\b(?:L')?Advocat\b", "Lawyer"), (r"^Arc de (\S+)", r"\1 Arch"),
          (r"^Bridge (?!(?:Street|Road|Lane)$)(.+)$", r"\1 Bridge"), (r"\bMgr\.? (?=[A-Z])", "Bishop "),
          (r"^Al-Barid Street$", "Post Office Street"), (r"^Montée (.+)$", r"\1 Rise"),
          (r"\b(?:Ste\.?|Saint) Mother Teresa\b", "Mother Teresa"), (r"\bSte\.? (?=[A-Z])", "Saint "),
          (r"\bSagese\b", "Sagesse"), (r"\s+-\s+(Road|Street|Lane|Highway)$", r" \1"),
          (r"^(Municipality|School|Church|University|Hospital|Monastery|Mosque) of ([^,]+)$", r"\2 \1"),
          (r"\bShit\b", "Chit"), (r"\bAlkornish\b", "Corniche"), (r"\bElcheikh\b", "Sheikh"), (r"\bSaint[- ]Rock\b", "Saint Roch"),
          (r"\s*\(Po[eè]te\)", ""), (r"\bBusros\b", "Bustros"), (r"\bBranjne\b", "Barajneh"), (r"`", ""),
          (r"\bOur Lady Church\b(?! (?:Street|Road|Lane|Way|Path|Stairs|Square|Passage)\b)", "Church of Our Lady"),
          (r"\bCaslte\b", "Castle"),
          (r"\bKamil Chamoun\b", "Camille Chamoun"), (r"\bSaints Pierre and Paul\b", "Saints Peter and Paul"),
          (r"\bMarie-Noel\b", "Marie-Noël"), (r"\s*\(Poet\)", ""), (r"\bCl[ée]op[aâ]tre\b", "Cleopatra"),
          (r"\bEmam\b", "Imam"), (r"\bSader\b", "Sadr"), (r"\bEamiliyeh\b", "Aamiliyeh"), (r"\bAl-Maaraz\b", "Maarad"),
          # French left in English names (an English name made from a French one)
          (r"\bMichel[- ]Ange\b", "Michelangelo"), (r"\bL[ée]onard de Vinci\b", "Leonardo da Vinci"),
          (r"\bCh[âa]teau de (\w+)", r"\1 Castle"), (r"\bMartyrs Assyriens\b", "Assyrian Martyrs"),
          (r"\b(\S+) General Road$", r"\1 Main Road"), (r"\bDotations\b", "Awqaf"), (r"\bVahchouch\b", "Yahchouch"),
          (r"\bPavillion\b", "Pavilion"), (r"\bAchie\b", "Ashir"), (r"\s*&\s*", " and "),
          (r"\b(Path|Street|Road|Lane|Way|Walk|Highway|Avenue|Square|Junction|Roundabout|Bridge|Tunnel|Stairs|Exit|"
           r"Entrance|Interchange|Passage|Boulevard|School|Church) \1\b", r"\1"),   # "Pavilion 2 Path Path", "Nejmeh Square Square"
          (r"\bJisr Al Qad\b", "Jisr Al Qadi"),
          (r"\bSa Sainteté le Pape\b", "His Holiness the Pope"), (r"\bPalais de Justice\b", "Palace of Justice"),
          (r"\b(Jbeil|Jbail) Byblos\b", r"\1"),
          (r"^Al-Thani Main Street$", "Second Main Street"), (r"\bParlement\b", "Parliament"),
          (r"\bMaisons Priv[ée]e?s?\b", "Private Houses"), (r"\bJasmins\b", "Jasmine"), (r"^Avenida Brasil$", "Brazil Avenue"),
          (r"^The (?=.+ (?:Street|Road|Lane|Avenue)$)", ""), (r"^Jacob Sarouf\b", "Yaacoub Sarrouf"), (r"\bAlias\b", "Elias"),
          (r"\bBrothers (\S+) (Street|Road|Lane|Avenue)$", r"\1 Brothers \2"),   # "Brothers Fleyfel Street"
          (r"^([A-Z]) (Lane|Street|Road)$", r"\2 \1"),                          # "B Lane" -> "Lane B"
          (r"\bAlexandre Pochkine\b", "Alexander Pushkin"), (r"\bRoi\b", "King"),
          (r"^(\d+) (?!Meters?\b|Metres?\b)((?:Al |El )?[A-Z]\w+) (Street|Road)$", r"\2 \3 \1"),   # "107 Mountazah Street"
          (r"\bClémenceau\b", "Clemenceau"), (r"\bJounie\b", "Jounieh"), (r"\bLa Poste\b", "Post Office"),
          (r"(?<=\w)- (?=\w)|(?<=\w) -(?=\w)", " - "),   # "Hiyata- Chahtoul", "Baskenta -Sannine"
          (r"^Hay (\S+) Square$", r"Hay \1"), (r"\bAbel Alhussein\b", "Abdel Hussein"),
          (r"^Umayyad Ruins of Aanjar\b", "Anjar Umayyad Ruins"), (r"^Cedar - ", "Cedars - "), (r"\bSahabi (?=[A-Z])", ""),
          (r"\bSainte?-(?=[A-Z])|\bSt-(?=[A-Z])|\bSt\.? (?=[A-Z])", "Saint "), (r"\bSaint Hanne\b", "Saint Anne"),
          (r"\bSaint Antonios\b", "Saint Anthony"), (r"\bCedres\b", "Cedar"),
          (r"^(.+?) (\d+) (Street|Road|Lane)$", r"\1 \3 \2"),   # "Kindergarten 2 Street" -> "Kindergarten Street 2"
          (r"\bTribunal Militaire\b", "Military Court"), (r"^Garage Mont [Ll]a Salle Street$", "Mont La Salle Garage Street")]
FIX_AR = [(r"الكرنتيتا", "الكرنتينا"), (r"\s*\((?:ع|ص|رض|قده|قدس سره)\)", ""),   # typo; honorifics "(ع)"
          (r"طرابس", "طرابلس"), (r"البرنجة", "البراجنة"), (r"عبد العدي", "عبد الهادي"), (r"الجبل لبناني", "جبل لبنان"),
          (r"(^|\s)إبن(?=\s)", r"\1ابن"), (r"إبتهاج", "ابتهاج"),
          (r"(^|\s)[أا]تستراد(?=\s|$)", r"\1أوتوستراد"),   # OSM's "أتستراد"
          (r"^(?!(?:ساحة|طريق|شارع|جادة|أوتوستراد)\s)(.+?) (?:ال)?(ساحة|طريق|شارع|أوتوستراد)$", r"\2 \1"),   # type first
          (r"^(طريق|شارع|جادة) (?=ال\1\s)", ""),             # "طريق الطريق العسكرية"
          (r"^(\d+) (شارع|طريق|جادة) (.+)$", r"\2 \3 \1"),   # "200 شارع السلاف" -> "شارع السلاف 200"
          (r"^شراع ", "شارع "), (r"^شارع مستشفى$", "شارع المستشفى"), (r"إمرؤ", "امرؤ"), (r"إرسلان", "أرسلان"),
          (r"\bعمر ابن العاص\b", "عمرو بن العاص"), (r"^تستراد ", "أوتوستراد "), (r"\bنفق سليم سليم\b", "نفق سليم سلام"),
          (r"^الرويس (?=شارع )", ""),   # "الرويس شارع كرواسون الطيب": the quarter, then the street's name
          (r"^سارع ", "شارع "), (r"بن خليفة الثاني\b", "بن خليفة آل ثاني"), (r"(^|\s)بسايا(?=\s|-|$)", r"\1بسابا"),
          (r"(?<=[ء-ي])-(?=[ء-ي])", " - "),               # "بسابا-سوق الغرب": a road between two places
          (r"^طريق الرئيسي (.+)$", r"طريق \1 الرئيسي"),   # "طريق الرئيسي تول - الدوير"
          (r"(^|\s)جناح المركزي(?=\s|$)", r"\1الجناح المركزي"), (r"(^|\s)مدرسة اليسوعية(?=\s|$)", r"\1المدرسة اليسوعية"),
          (r"(^|\s)جميزة(?=\s|$)", r"\1الجميزة"),
          (r"^(شارع|طريق) (\d+) (?!متر)(\S+)$", r"\1 \3 \2"),   # "شارع 107 المنتزه" -> "شارع المنتزه 107"
          (r"صغبين بحيرة إطلالة", "صغبين - إطلالة البحيرة"),   # "Saghbine - Lake View", transcribed word by word
          (r"(^|\s)أرز(?=\s|$)", r"\1الأرز"), (r"(^|\s)الكاراج مون لاسال", r"\1كاراج مون لاسال"),
          (r"(^|\s)رفيق حريري(?=\s|$)", r"\1رفيق الحريري"), (r"قاب إلياس", "قب الياس"), (r"(^|\s)صنائع(?=\s|$)", r"\1الصنائع"),
          (r"(^|\s)البير نقاش(?=\s|$)", r"\1ألبير نقاش"), (r"^(تقاطع|مفترق|طريق|مستديرة|دوار) الغزير(?=\s|$)", r"\1 غزير"),
          (r"^(?!مستديرة\s)(.+?) مستديرة$", r"مستديرة \1"),   # "الزعرور - بتغرين مستديرة", English word order
          # "Zaarour - Bteghrine Roundabout" read as two names: one roundabout between two places
          (r"^(?!.*(?:^|\s)(?:طريق|شارع|أوتوستراد|اوتوستراد|جادة|جسر|نفق|ساحة)\s)(.+?) - مستديرة (.+)$", r"مستديرة \1 - \2"),
          (r"القديس بطرس وبولس", "القديسين بطرس وبولس"), (r"باتريسيا أليكسندروس", "البطريرك ألكسندروس"),   # Patricia for "Patriarch"
          (r"(^|\s)ىحال(?=\s|$)", r"\1رحال"), (r"(^|\s)جبل لاسال(?=\s|$)", r"\1مون لاسال"),
          # a noun before its adjective keeps the article: "ممر الجامع القديم", not "ممر جامع القديم" (not
          # "الجديدة", also a town: "مدرسة الجديدة" is Jdeideh's school)
          (r"(^|\s)(جامع|مسجد|كنيسة|مدرسة|سوق) (?=(?:القديم|القديمة|الكبير|الكبيرة)(?:\s|$))", r"\1ال\2 ")]
# French words left in English names, and landmark nouns English puts last ("Église Mar Elias" ->
# "Mar Elias Church").
FR_EN_WORDS = {"Père": "Father", "Sœur": "Sister", "Frère": "Brother", "Frères": "Brothers", "Mère": "Mother",
               "Patriarche": "Patriarch", "Patriarcat": "Patriarchate", "Syriaque": "Syriac", "Douanes": "Customs",
               "Jardins": "Gardens", "Jardin": "Garden", "Perses": "Persians", "Monseigneur": "Monsignor",
               "Cheikh": "Sheikh", "Docteur": "Doctor", "Président": "President", "Général": "General", "Émir": "Emir",
               "Écoles": "Schools", "Émigrés": "Emigrants", "Église": "Church", "École": "School", "Collège": "College",
               "Université": "University", "Municipalité": "Municipality", "Hôpital": "Hospital", "Mosquée": "Mosque",
               "Couvent": "Monastery", "Lycée": "High School", "Quarantaine": "Karantina", "Piscine": "Swimming Pool",
               "Internationale": "International", "Beyrouth": "Beirut", "Damas": "Damascus", "Maritime": "Coastal",
               "Orthodoxe": "Orthodox", "Catholique": "Catholic", "Arménienne": "Armenian", "Grecque": "Greek",
               "Évangélique": "Evangelical", "Jésuite": "Jesuit", "Jésuites": "Jesuits", "Pères": "Fathers",
               "Carmes": "Carmelite", "Nouveau": "New", "Nouvelle": "New", "Cimetière": "Cemetery", "Grande": "Great",
               "Grand": "Great", "Séminaire": "Seminary", "Ouadi": "Wadi", "Aïn": "Ain", "Justinien": "Justinian",
               "Papinien": "Papinian", "Secteur": "Sector", "Mexique": "Mexico", "Chili": "Chile", "Alger": "Algiers",
               "Gare": "Station", "Château": "Castle", "Pacha": "Pasha", "Béni": "Bani", "Vénus": "Venus",
               "Assyriens": "Assyrian", "Arméniens": "Armenian", "Wakfs": "Awqaf", "Pavillon": "Pavilion",
               "Mer": "Sea", "Liban": "Lebanon", "Armée": "Army", "Chevaliers": "Knights", "Martyrs": "Martyrs'",
               "Maternelle": "Kindergarten", "Ferme": "Farm", "Brésil": "Brazil", "Syrie": "Syria",
               "Kurdes": "Kurds", "Amérique": "America", "Professeur": "Professor", "Pere": "Father", "Mere": "Mother",
               "Poste": "Post Office"}
EN_NOUN_LAST = {"Church", "School", "College", "University", "Municipality", "Hospital", "Mosque", "Monastery",
                "High School", "Swimming Pool"}


def _fix(name, fixes):
    for pattern, repl in fixes:
        name = re.sub(pattern, repl, name)
    return name


SCHOLARLY = str.maketrans({"ʿ": "", "ʾ": "", "ż": "z", "Ż": "Z", "ḥ": "h", "Ḥ": "H", "ṣ": "s", "Ṣ": "S", "ṭ": "t",
                            "Ṭ": "T", "ḍ": "d", "Ḍ": "D", "ẓ": "z", "ā": "a", "Ā": "A", "ī": "i", "Ī": "I", "ū": "u",
                            "Ū": "U"})


# Mandate-era spellings with circumflexes ("Bhamdoûn", "Mâr Eliâs", "Nabatîyé") as Lebanon writes
# them today; French words keep theirs ("Rue des Mûriers").
FR_CIRCUMFLEX = {"mûrier", "mûriers", "mûre", "mûres", "châtaignier", "châtaigniers", "château", "châteaux",
                 "benoît", "cléopâtre", "théâtre", "maître", "île", "îles", "pâtisserie", "apôtre", "apôtres",
                 "cloître", "plâtre", "grâce", "grâces", "âge", "bâtiment", "bâtiments", "sûreté", "voûte", "goût",
                 "coût", "août", "croûte", "gîte", "huître", "huîtres", "abîme", "fraîche", "chaîne", "câble",
                 "pâques", "pâturage", "pâturages", "bâton", "âme", "âne", "gâteau", "gâteaux", "crâne", "sûr",
                 "jeûne", "flûte", "brûlé", "brûlée", "fût", "épître", "dîme", "pâtre", "châtelain"}
PLAIN_VOWELS = str.maketrans("âîûÂÎÛ", "aiuAIU")


def modern_spelling(name):
    if not isinstance(name, str) or not re.search("[âîûÂÎÛ]", name):
        return name
    return re.sub(r"\w+", lambda m: m.group(0) if m.group(0).lower() in FR_CIRCUMFLEX
                  else m.group(0).translate(PLAIN_VOWELS), name)


FR_TYPE_HEAD = re.compile(r"^(Rue|Route|Avenue|Place|Impasse|Passage|Chemin|Allée|Ruelle|Boulevard) "
                          r"(?!(?:de|du|des|d'|la|le|les|l')\b|Port[- ]Sa)(\S.*)$")   # not Port-Saïd, a city


def fix_fr(name):
    """French names cleaned of OSM slips, with the article a common noun takes ("Rue Château de
    Beaufort" -> "Rue du Château de Beaufort") and capitals after it ("Rue de l'armée" -> "Rue de
    l'Armée")."""
    if not isinstance(name, str):
        return name
    name = _fix(modern_spelling(name.translate(SCHOLARLY)), FIX_FR)
    m = FR_TYPE_HEAD.match(name)
    if m and strip_accents(re.split(r"[\s\-]", m.group(2))[0].lower()) in FR_FEMININE | FR_MASCULINE:
        name = f"{m.group(1)} {fr_of(m.group(2))}"
    return re.sub(r"^(\S+ (?:de l'|de la |du |des ))([a-zàâçéèêëîïôûùüÿœ])", lambda m: m.group(1) + m.group(2).upper(), name)


def _match_form(word):
    """A Latin word by its sounds, so spellings of one Arabic word agree: 'Chéhab' and 'Shehab' ->
    'sehab', 'Naccache' and 'Nakkash' -> 'nakase'."""
    w = strip_accents(word.lower())
    for a, b in (("sch", "s"), ("sh", "s"), ("ch", "s"), ("kh", "h"), ("gh", "g"), ("dj", "j"), ("th", "t"),
                 ("dh", "d"), ("ph", "f"), ("ou", "u"), ("oo", "u"), ("w", "u"), ("q", "k"), ("ck", "k"), ("c", "k"),
                 ("y", "i"), ("ee", "i"), ("ei", "i"), ("aa", "a")):
        w = w.replace(a, b)
    return re.sub(r"(?<=[aeiou])h$", "", re.sub(r"(.)\1+", r"\1", w))   # "Hikmeh", "Hikmé"


MATCH_SKIP = {"rue", "route", "avenue", "boulevard", "impasse", "ruelle", "passage", "autoroute", "place", "corniche",
              "chemin", "allee", "escalier", "montee", "descente", "sortie", "entree", "echangeur", "carrefour",
              "rond", "point", "street", "road", "lane", "highway", "square", "way", "path", "walk", "stairs", "exit",
              "entrance", "junction", "interchange", "roundabout", "de", "du", "des", "la", "le", "les", "al", "el",
              "an", "ar", "as", "at", "ad", "ed", "er", "es", "et", "en", "ech", "ej", "ez", "ash", "the", "of", "and",
              "saint", "sainte", "st", "mar", "dr", "abd", "abdel", "abdul", "abou", "abu", "bou", "ibn", "bin", "ben",
              "main", "principale", "principal", "general", "old", "new", "nouvelle", "ancienne", "president",
              "sheikh", "cheikh", "imam", "emir", "docteur", "doctor", "pere", "father", "notre", "dame", "our",
              "lady", "eglise", "church", "ecole", "school", "mosquee", "mosque", "haj", "hajj", "sayyed", "sayed",
              "oua", "wa", "w", "ou"}   # "Homs Oua Hama": the و of "حمص وحمى"


def _match_words(text):
    words = re.sub(r"[^a-z0-9]+", " ", strip_accents(text.lower())).split()
    return [w for w in words if w not in MATCH_SKIP and not w.isdigit() and len(w) > 1]


# Consonants alone, from either script: "بشري" and "Bcharré" are both "bsr", "فنيدق" and "Fnaydeq"
# "fndk" (long vowels, ayn and hamza drop out, as Latin spellings of them vary).
AR_SKELETON = {"ب": "b", "ت": "t", "ط": "t", "ث": "t", "ج": "j", "ح": "h", "ه": "h", "خ": "h", "د": "d", "ض": "d",
               "ذ": "s", "ز": "s", "ظ": "d", "ر": "r", "س": "s", "ص": "s", "ش": "s", "غ": "g", "ف": "f", "ق": "k",
               "ك": "k", "ل": "l", "م": "m", "ن": "n"}   # z and s, ظ and d: Latin spellings mix them ("Dhayra", "Bourghos")


def _ar_skeleton(word):
    word = word[2:] if word.startswith("ال") and len(word) > 3 else word
    return re.sub(r"(.)\1+", r"\1", "".join(AR_SKELETON.get(c, "") for c in word))


def _latin_skeleton(word):
    w = _match_form(word).replace("x", "ks").replace("p", "b").replace("v", "f").replace("z", "s")
    return re.sub(r"(.)\1+", r"\1", re.sub(r"[aeiou]", "", w))


def latin_matches(latin, arabic, every=False):
    """True when a Latin name names what the Arabic one does: most of its words (`every`: all of
    them) sound like the Arabic's words, as the dictionaries spell them or by their consonants.
    "Rue Alfred Naccache" matches "شارع ألفريد نقاش"; "Rue Mar Dimitrious", also tagged on that road
    in OSM, does not."""
    if not (isinstance(latin, str) and has_arabic(arabic)):
        return False
    words = _match_words(latin)
    if not words:
        return False
    enough = (lambda hits, n: hits == n) if every else (lambda hits, n: 2 * hits > n)
    ref = [w for lang in ("fr", "en") for w in _match_words(ar_street_to_latin(arabic, lang))]
    forms = [_match_form(r) for r in ref]
    forms += [_match_form("".join(ref[i:i + n])) for n in (2, 3) for i in range(len(ref) - n + 1)]
    ar_words = [w for w in re.split(r"[\s\-]+", re.sub(r"[ً-ْـ]", "", arabic))
                if has_arabic(w) and w.removeprefix("ال") not in AR_STREET_TYPES]   # not "شارع": "sr" is no name
    # A translation does not sound like the Arabic but reads back as it: "Rue de la Gare" is "شارع
    # المحطة", "Chemin Pavillon 2" "درب جناح 2".
    norm = lambda w: lex_ar_key(w).replace("ة", "ه").removeprefix("ال")
    target = {norm(w) for w in ar_words}
    back = [norm(w) for w in latin_to_ar(latin).split() if has_arabic(w) and w.removeprefix("ال") not in AR_STREET_TYPES]
    if back and enough(sum(w in target for w in back), len(back)):
        return True
    skeletons = [_ar_skeleton(w) for w in ar_words]
    skeletons += [_ar_skeleton("أ" + w[1:]) for w in ar_words if w.startswith("ال")]   # "البير" is also Albert
    skeletons += [_ar_skeleton(ar_words[i]) + _ar_skeleton(ar_words[i + 1]) for i in range(len(ar_words) - 1)]
    skeletons = [s for s in skeletons if s]

    def sounds(word):
        # The construct form is the same word: "Minet" (مينا), "Qalaat" (قلعة), "Haret" (حارة).
        for w in {word, word[:-1]} if re.search(r"[aeiou]t$", word) else {word}:
            f, s = _match_form(w), _latin_skeleton(w)
            if any(SequenceMatcher(None, f, r).ratio() >= 0.75 or len(f) >= 4 and (r.startswith(f) or r.endswith(f))
                   for r in forms) or any(s == k or min(len(s), len(k)) >= 3 and SequenceMatcher(None, s, k).ratio() >= 0.8
                                          for k in skeletons):
                return True
        return False
    return enough(sum(map(sounds, words)), len(words)) or same_sounds(latin, arabic)


def same_sounds(latin, arabic):
    """One name written in one word in Arabic and two in Latin, or the other way: "كفركيلا" / "Kfar
    Kila", "كفرنبرخ" / "Kfar Nabrakh" (their consonants, all words together)."""
    ar_words = [w for w in re.split(r"[\s\-]+", re.sub(r"[ً-ْـ]", "", arabic))
                if has_arabic(w) and w.removeprefix("ال") not in AR_STREET_TYPES]
    whole_ar = "".join(_ar_skeleton(w) for w in ar_words)
    whole_lat = "".join(map(_latin_skeleton, _match_words(latin)))
    return len(whole_ar) >= 4 and SequenceMatcher(None, whole_ar, whole_lat).ratio() >= 0.85


def sounds_like(a, b):
    """Two Latin spellings of one place, with or without the article: "Bent Jbayl" and "Bent Jbeil",
    "Ech-Chouf" and "Chouf", "Matn" and OCHA's "El Meten"."""
    bare = lambda s: re.sub(r"^(?:e[lnrsdtzj]|a[lnrsdtz]|ech|ach|ash)[- ]", "", strip_accents(s.lower()))
    a, b = bare(a), bare(b)
    return SequenceMatcher(None, _match_form(a), _match_form(b)).ratio() >= 0.8 \
        or len(_latin_skeleton(b)) >= 3 and _latin_skeleton(a) == _latin_skeleton(b)


def fix_en(name):
    """English names cleaned of OSM slips and French words: 'Patriarche Sfeir Street' -> 'Patriarch
    Sfeir Street', 'Église Saint-Joseph Lane' -> 'Saint-Joseph Church Lane'."""
    if not isinstance(name, str):
        return name
    name = _fix(modern_spelling(name.translate(SCHOLARLY)), FIX_EN)
    words = name.split(" ")
    tail = [words.pop()] if len(words) > 1 and words[-1].lower() in EN_STREET_END | {"lane", "passage", "avenue"} else []
    french_noun = words[0] in FR_EN_WORDS   # only a noun translated from French moves: "Église Saint-Joseph"
    words = [FR_EN_WORDS.get(w) or "-".join(FR_EN_WORDS.get(p, p) for p in w.split("-")) for w in words]   # "Beyrouth-Damas" too
    if french_noun and len(words) > 1 and words[0] in EN_NOUN_LAST and words[1].lower() not in ("of", "in", "at", "on"):
        words = words[1:] + words[:1]
    return _fix(" ".join(words + tail), FIX_EN)   # again, on the translated words: "Mer Highway" -> "Coastal Highway"


def fix_ar(name):
    """Arabic names as written: OSM's 'مرجعيون - طريق جزين' -> 'طريق مرجعيون - جزين', 'الطريق
    السريع المرج' -> 'أوتوستراد المرج', no honorific '(ع)', known typos fixed."""
    if not isinstance(name, str) or not has_arabic(name):
        return name
    name = _fix(BIDI_MARKS.sub("", name), FIX_AR).strip()
    m = re.fullmatch(r"(.+?)\s*-\s*(شارع|طريق|جادة|أوتوستراد|اوتوستراد|أتستراد)\s+(.+)", name)
    if m and not any(name.startswith(t + " ") for t in AR_STREET_TYPES) \
            and not re.match(r"(نفق|جسر|مدخل|مخرج|تقاطع|دوار|مستديرة|ساحة)\s", name):   # "نفق سليم سلام - أوتوستراد البحر": two names
        name = f"{m.group(2)} {m.group(1)} - {m.group(3)}"
    words = name.split()
    if len(words) > 1 and words[0] in ("الطريق", "الشارع") and _match_place(words, 1, GAZETTEER_AR, _ar_key)[0]:
        name = " ".join([words[0][2:]] + words[1:])   # "الطريق المقيبلة الرئيسي" -> "طريق المقيبلة الرئيسي"
    return re.sub(r"^(?:ال)?طريق السريع\s+(?=\S)", "أوتوستراد ", name)


EN_STREET_END = {"street", "road", "highway", "lane", "square", "st", "rd"}


def looks_english(name):
    """'Sea Highway' in a name:fr tag is English."""
    words = name.lower().rstrip(".").split() if isinstance(name, str) else []
    return len(words) > 1 and words[-1] in EN_STREET_END and words[0] not in {"rue", "route", "avenue", "impasse"}


def cap_en(name):
    """English capitalisation: 'saint Antoine church Lane' -> 'Saint Antoine Church Lane'; short
    words (of, the, ibn, al) stay as they are after the first."""
    if not isinstance(name, str):
        return name
    return " ".join(w[:1].upper() + w[1:] if (i == 0 or len(w) > 3 and w[1:2] != "'") and w[:1].islower() else w
                    for i, w in enumerate(name.split(" ")))   # "Jeanne d'Arc", not "D'Arc"


def cap_fr(name):
    """French capitalisation: only the first letter ('el-Aqaba - Joun' -> 'El-Aqaba - Joun')."""
    return name[:1].upper() + name[1:] if isinstance(name, str) else name


# Latin adjectives -> Arabic (masculine, feminine), placed after the noun.
LATIN_ADJECTIVES = {"main": ("الرئيسي", "الرئيسية"), "principale": ("الرئيسي", "الرئيسية"),
                    "principal": ("الرئيسي", "الرئيسية"), "old": ("القديم", "القديمة"),
                    "upper": ("العلوي", "العلوية"), "lower": ("السفلي", "السفلية"),
                    "international": ("الدولي", "الدولية"), "internationale": ("الدولي", "الدولية")}
ACRONYM = re.compile(r"^(?:[A-Z]{1,5}|(?:[A-Za-z]\.){1,5}[A-Za-z]?\.?)$")
REVIEWED_LATIN_KEYS = {_latin_key(k): v for k, v in REVIEWED_LATIN.items()}
TRANSCRIBED_LATIN_KEYS = {_latin_key(k): v for k, v in TRANSCRIBED_LATIN.items()}
LATIN_LOOKUP = {**TRANSCRIBED_LATIN_KEYS, **REVIEWED_LATIN_KEYS}


def _latin_tokens(text):
    return [t.strip("(),") for t in re.split(r"[\s\-'’]+", re.sub(r"['’]s\b", "", text)) if t.strip("(),")]


def is_transcribed(text):
    """True when a Latin name's Arabic relies on a transcription (TRANSCRIBED_LATIN): no Arabic
    original was found for some word."""
    if not isinstance(text, str) or has_arabic(text):
        return False
    tokens = _latin_tokens(text)
    return _latin_key(text) in TRANSCRIBED_LATIN_KEYS or any(
        _match_place(tokens, i, TRANSCRIBED_LATIN_KEYS, _latin_key, longest=5)[0] for i in range(len(tokens)))

LATIN_PHRASES = {"police station": "مخفر", "public garden": "حديقة عامة", "high school": "ثانوية",
                 "public school": "مدرسة رسمية", "municipal stadium": "ملعب بلدي", "town hall": "بلدية"}


def latin_to_ar(text, report=None):
    """French/English name -> rough Arabic name, type word first and adjectives last ("Old Souk
    Hasroun" -> "سوق حصرون القديم"). Reports letter-by-letter words."""
    if _latin_key(text) in LATIN_LOOKUP:
        return spell_latin_in_arabic(LATIN_LOOKUP[_latin_key(text)])
    parts = re.split(r"\s+-\s+", text.strip())
    last = strip_accents(parts[-1].split()[-1].lower()).rstrip(".") if parts[-1].split() else ""
    if len(parts) > 1 and last not in ROAD_TYPES:
        # "Sea Highway - Nahr El Mot Bridge": two names, each with its own type word.
        return " - ".join(latin_to_ar(p, report) for p in parts)
    text = re.sub(r"['’]s\b", "", text)          # "Farah's Garden"
    text = re.sub(r"(?i)\brond[- ]point\b", "Roundabout", text)   # "Rond-point Louaizé": مستديرة, not "روند بوانت"
    text = re.sub(r"\b[AaEe][tnsdrz]-(?=\w)", "al ", text)   # "At-Tawil", "En-Naqoura": the article
    low = strip_accents(text.lower())
    lead = None
    for phrase, ar in LATIN_PHRASES.items():
        if low.endswith(" " + phrase):
            text, lead = text[:-len(phrase) - 1], ar
            break
    tokens = [t.strip("(),") for t in re.split(r"[\s\-'’]+", text) if t.strip("(),")]
    types = []   # trailing type words go first, outermost first: "Sea Highway Entrance" -> "مدخل أوتوستراد البحر"
    while lead is None and len(tokens) > 1 and strip_accents(tokens[-1].lower()) in EN_TRAILING_TYPES:
        word = tokens.pop()
        types.append({"st": "street", "rd": "road", "ave": "avenue"}.get(strip_accents(word.lower()).rstrip("."), word))
    tokens = types + tokens
    adjectives = [k for t in tokens if (k := strip_accents(t.lower())) in LATIN_ADJECTIVES]
    tokens = [t for t in tokens if strip_accents(t.lower()) not in LATIN_ADJECTIVES]
    out = [lead] if lead else []
    i, article = 0, False
    while i < len(tokens):
        key = strip_accents(tokens[i].lower()).strip(".,()")
        if key in LATIN_ARTICLES and i + 1 < len(tokens):   # "Al Jabal" -> "الجبل"
            article, i = True, i + 1
            continue
        reviewed, n = _match_place(tokens, i, LATIN_LOOKUP, _latin_key, longest=5)
        place, m = _match_place(tokens, i, GAZETTEER_LATIN, _latin_key)
        if reviewed and n >= m:
            word, i = reviewed, i + n
        elif place:
            word, i = place, i + m
        else:
            i += 1
            if i > 1 and tokens[i - 1] in ROMAN:   # "Nyareb I": the first, not the letter آي
                word = ROMAN[tokens[i - 1]]
            elif key in THEME_LATIN and i > 1 and strip_accents(tokens[i - 2].lower()).strip(".") in PERSON_TITLES:
                word = GIVEN_AR.get(key) or _latin_word_to_ar(key)   # "Mère Marguerite": a name, not the daisy
                if key not in GIVEN_AR and report is not None:
                    report.append(key)
            elif key in LATIN_WORDS:
                word = LATIN_WORDS[key]
            elif any(ch.isdigit() for ch in key):
                word = key
            elif key in LEXICON["ar"]:
                word = LEXICON["ar"][key]
            elif ACRONYM.match(tokens[i - 1]):
                word = tokens[i - 1]   # "WBCC", "F.R.A.", initials: kept in Latin letters
            else:
                word = _latin_word_to_ar(key) if key else ""
                if word and report is not None:
                    report.append(key)
        if word:
            out.append("ال" + word if article and has_arabic(word) and not word.startswith("ال") else word)
        article = False
    if adjectives and out:
        # Arabic adjectives follow the noun and agree with it: "طريق عنجر الرئيسية", "الشارع الرئيسي".
        feminine = out[0] in ("طريق", "ساحة") or out[0].endswith("ة")
        if len(out) == 1:
            out[0] = "ال" + out[0]
        out += [LATIN_ADJECTIVES[a][1 if feminine else 0] for a in dict.fromkeys(adjectives)]
    out = [w for k, w in enumerate(out) if k == 0 or w != out[k - 1]]   # "Blat Jbeil Byblos": جبيل once
    return spell_latin_in_arabic(" ".join(out))


def latin_like(a, b):
    """Two Latin names of one thing: most words of `a` sound like words of `b` ("Cardinal Jebrayel
    Tabbouni" tagged name:en "Alfred Naccache Road" is not)."""
    words, ref = _match_words(a), [_match_form(w) for w in _match_words(b)]
    hits = sum(any(SequenceMatcher(None, _match_form(w), r).ratio() >= 0.75 for r in ref) for w in words)
    return bool(words) and 2 * hits > len(words)


# French noun gender for "Rue de la / du / de l'" composition.
FR_FEMININE = {"eglise", "ecole", "mosquee", "chapelle", "cathedrale", "basilique", "mairie", "municipalite",
               "universite", "faculte", "source", "place", "gare", "poste", "bibliotheque", "caserne",
               "clinique", "citadelle", "tour", "fontaine", "plage", "grotte", "foret", "colline", "vallee",
               "maison", "residence", "station", "cite", "piscine", "corniche", "usine", "autoroute", "zone"}
FR_MASCULINE = {"college", "casino", "lycee", "couvent", "monastere", "hopital", "institut", "parc", "jardin", "stade",
                "musee", "chateau", "temple", "sanctuaire", "marche", "palais", "port", "phare", "pont",
                "centre", "complexe", "club", "cimetiere", "souk", "serail", "khan", "fort", "lac", "sommet",
                "mont", "mausolee", "monument", "memorial", "site", "theatre", "quartier", "campus",
                "seminaire", "patriarcat", "eveche", "archeveche", "dispensaire", "orphelinat", "hammam", "secteur"}
FR_NO_ARTICLE = ("saint", "sainte", "st ", "st-", "ste ", "ste-", "notre-dame", "notre dame", "mar ")


def fr_of(name):
    """'Église Saint-Élie' -> "de l'Église Saint-Élie"; proper names stay bare ("Rue Mar Elias")."""
    low = strip_accents(name.lower())
    if low.startswith(FR_NO_ARTICLE):
        return name
    if low.startswith("poste de police"):   # le poste de police; la poste is the post office
        return "du " + name
    for art, rep in (("le ", "du "), ("les ", "des "), ("la ", "de la "), ("l'", "de l'"), ("l’", "de l'")):
        if low.startswith(art):
            return rep + name[len(art):]
    parts = re.split(r"[\s\-]", low)
    first = parts[1] if len(parts) > 1 and parts[0] in ("grand", "grande", "nouveau", "nouvelle", "ancien",
                                                      "ancienne", "vieux", "vieille", "petit", "petite") else parts[0]
    if first in FR_FEMININE and parts[0] != first:
        return ("de l'" if low[0] in "aeiouh" else "de la ") + name
    if first in FR_MASCULINE and parts[0] != first:
        return ("de l'" if low[0] in "aeiouh" else "du ") + name
    if first in FR_FEMININE:
        return ("de l'" if first[0] in "aeiouh" else "de la ") + name
    if first in FR_MASCULINE:
        return ("de l'" if first[0] in "aeiouh" else "du ") + name
    return name


def fr_route_to(town):
    """'Route de Bikfaya', "Route d'Aley"; a place named in French takes its article ("Route du Port
    de Beyrouth", "Route de la Cité industrielle"), an Arabic name does not ("Route de Souk El Gharb")."""
    words = town.split()
    french = (" de " in town or any(w[:1].islower() for w in words[1:])) \
        and not re.search(r"(?i)\b(?:el|al|ech|ach|es|ez|ed|er|en|ej)\b", town)
    if french and fr_of(town) != town:
        return fr_of(town)
    return ("d'" if strip_accents(town[:1].lower()) in "aeiouh" else "de ") + town


# Leading Arabic street-type word -> (French prefix, English suffix).
AR_STREET_TYPES = {
    "شارع": ("Rue", "Street"), "طريق": ("Route", "Road"), "جادة": ("Avenue", "Avenue"),
    "أوتوستراد": ("Autoroute", "Highway"), "اوتوستراد": ("Autoroute", "Highway"), "أتستراد": ("Autoroute", "Highway"),
    "اتستراد": ("Autoroute", "Highway"), "كورنيش": ("Corniche", "Corniche"), "كرنيش": ("Corniche", "Corniche"),
    "زاروب": ("Ruelle", "Lane"), "زقاق": ("Ruelle", "Lane"), "ساحة": ("Place", "Square"), "درج": ("Escalier", "Stairs"),
    "بوليفارد": ("Boulevard", "Boulevard"), "بولفار": ("Boulevard", "Boulevard"), "تقاطع": ("Carrefour", "Junction"),
    "مستديرة": ("Rond-point", "Roundabout"), "دوار": ("Rond-point", "Roundabout"), "عبور": ("Passage", "Crossing"),
    "ممر": ("Passage", "Passage"), "منحدر": ("Descente", "Descent"), "مخرج": ("Sortie", "Exit"),
    "باحة": ("Parvis", "Courtyard"), "الوصول": ("Arrivées", "Arrivals"), "المغادرة": ("Départs", "Departures"),
    "ممشى": ("Allée", "Walk"),
    # OSM typos for شارع
    "سارع": ("Rue", "Street"), "شراع": ("Rue", "Street"), "شاري": ("Rue", "Street"),
}


# Two-word type phrases -> (French, English, French takes "de"), also when written last
# ("مزبود الطريق العام").
AR_STREET_PHRASES = {
    "طريق السريع": ("Autoroute", "Highway", False), "الطريق السريع": ("Autoroute", "Highway", False),
    "الطريق العام": ("Route principale", "Main Road", True), "الطريق الرئيسي": ("Route principale", "Main Road", True),
    "الطريق الرئيسية": ("Route principale", "Main Road", True), "الشارع الرئيسي": ("Rue principale", "Main Street", True),
    "الشارع العام": ("Rue principale", "Main Street", True),
}
FR_ADJ_ALONE = {"Nouveau": ("Neuf", "Neuve"), "Nouvelle": ("Neuf", "Neuve"), "Ancien": ("Ancien", "Ancienne"),
                "Ancienne": ("Ancien", "Ancienne"), "Grand": ("Grand", "Grande"), "Grande": ("Grand", "Grande"),
                "Principale": ("Principal", "Principale")}
FR_FEMININE_TYPES = {"Rue", "Route", "Avenue", "Place", "Autoroute", "Impasse", "Ruelle", "Allée", "Corniche"}
AR_MAIN = {"الرئيسي", "الرئيسية", "رئيسي", "رئيسية"}   # "طريق شحيم الرئيسي": main road
AR_MAIN_ROAD = {"عام", "العام"}                        # only after طريق: "طريق عام مستيتا"
# A road named after a town, new or old: "طريق صيدا القديمة" -> "Ancienne route de Saïda" / "Old Saida Road".
AR_ROAD_AGE = {"الجديد": ("Nouvelle", "New"), "الجديدة": ("Nouvelle", "New"), "القديم": ("Ancienne", "Old"),
               "القديمة": ("Ancienne", "Old")}


def ar_street_to_latin(name, lang="fr", report=None, sources=None):
    """'شارع الحمرا' -> 'Rue el-Hamra' / 'el-Hamra Street'; 'مخرج طريق المطار' -> 'Sortie Route de
    l'Aéroport' / 'Airport Road Exit'; 'طريق شحيم الرئيسي' -> 'Route principale de Chehim' /
    'Chehim Main Road'."""
    name = name.strip()
    for phrase in AR_STREET_PHRASES:
        if name.endswith(" " + phrase):
            name = f"{phrase} {name[:-len(phrase) - 1]}"
            break
    for phrase, (fr_type, en_type, de) in AR_STREET_PHRASES.items():
        if name.startswith(phrase + " "):
            body = ar_street_to_latin(name[len(phrase) + 1:], lang, report, sources)
            return (f"{fr_type} {fr_route_to(body) if de else body}" if lang == "fr" else f"{body} {en_type}")
    head, _, rest = name.partition(" ")
    head = head[2:] if head.startswith("ال") and head[2:] in AR_STREET_TYPES and rest else head   # "الشارع القديم"
    if head in AR_STREET_TYPES and rest:
        fr_type, en_type = AR_STREET_TYPES[head]
        words = rest.split()
        main = AR_MAIN | (AR_MAIN_ROAD if head == "طريق" else set())
        if any(w in main for w in words) and not all(w in main for w in words):
            body = ar_street_to_latin(" ".join(w for w in words if w not in main), lang, report, sources)
            return f"{fr_type} principale {fr_route_to(body)}" if lang == "fr" else f"{body} Main {en_type}"
        if head == "طريق" and len(words) > 1 and words[-1] in AR_ROAD_AGE:
            age_fr, age_en = AR_ROAD_AGE[words[-1]]
            body = ar_street_to_latin(" ".join(words[:-1]), lang, report, sources)
            return f"{age_fr} route {fr_route_to(body)}" if lang == "fr" else f"{age_en} {body} {en_type}"
        body = ar_street_to_latin(rest, lang, report, sources)
        if lang == "fr" and body in FR_ADJ_ALONE:   # "شارع الجديد": "Rue Neuve", not "Rue Nouveau"
            masc, fem = FR_ADJ_ALONE[body]
            return f"{fr_type} {fem if fr_type in FR_FEMININE_TYPES else masc}"
        if lang == "en" and re.search(r"\s\d+$", body):   # "University Street 1", not "University 1 Street"
            name_part, number = body.rsplit(" ", 1)
            return f"{name_part} {en_type} {number}"
        return f"{fr_type} {fr_of(body)}" if lang == "fr" else f"{body} {en_type}"
    return ar_to_latin(name, lang, report, sources)


EN_TO_FR_TYPES = [  # longest first
    ("police station", "Poste de police"), ("public garden", "Jardin public"), ("public school", "École publique"),
    ("municipal stadium", "Stade municipal"), ("town hall", "Mairie"), ("high school", "Lycée"), ("intermediate school", "Collège"), ("church", "Église"), ("school", "École"),
    ("mosque", "Mosquée"), ("hospital", "Hôpital"), ("university", "Université"), ("park", "Parc"),
    ("garden", "Jardin"), ("stadium", "Stade"), ("municipality", "Municipalité"), ("monastery", "Couvent"),
    ("convent", "Couvent"), ("library", "Bibliothèque"), ("museum", "Musée"), ("spring", "Source"),
    ("square", "Place"), ("center", "Centre"), ("centre", "Centre"), ("cathedral", "Cathédrale"),
    ("chapel", "Chapelle"), ("college", "Collège"), ("institute", "Institut"), ("shrine", "Sanctuaire"),
]


# Arabizi words (digits for Arabic letters) found in Latin street names.
ARABIZI = {"tal3it": "Taleet", "tal3et": "Taleet", "tal3a": "Taleet", "7ay": "Hay", "7aret": "Haret",
           "3ein": "Aïn", "3ain": "Ain", "3in": "Ain"}


def tidy(name):
    """Title-case names typed all in lowercase ('official secondary saadnayel'); spell Arabizi
    words with letters ('Tal3it El Knise' -> 'Taleet El Knise'); drop stray Arabic vowel marks
    from Latin names ('ِِAyn El Mrayseh')."""
    if not isinstance(name, str):
        return name
    name = re.sub(r"(?i)\bround[- ]about\b", "Roundabout", BIDI_MARKS.sub("", name))
    bare = re.sub(r"[ً-ْـ]", "", name)
    name = bare if has_latin(bare) and not has_arabic(bare) else name
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\b\w*\d\w*\b", lambda m: ARABIZI.get(m.group(0).lower(), m.group(0)), name)
    shouted = re.findall(r"\b[A-Z]{4,}\b", name)   # "Rue SALIM HIJAZI & BILAL AZAM"; not "WBCC", "LAU"
    if len([w for w in shouted if re.search("[AEIOUY]", w)]) >= 2:
        name = re.sub(r"\b[A-Z]{4,}\b", lambda m: m.group(0).capitalize() if re.search("[AEIOUY]", m.group(0))
                      else m.group(0), name)
    return name.title() if name == name.lower() and has_latin(name) else name


def en_to_fr(name):
    """'St. Joseph Church' -> 'Église Saint Joseph' (English landmark names lacking a French tag)."""
    low = name.lower().strip()
    out = name.strip()
    for en, fr in EN_TO_FR_TYPES:
        if low.endswith(" " + en):
            out = f"{fr} {out[:-len(en) - 1].strip()}"
            break
    return re.sub(r"\bSt\.?(?=\s)", "Saint", out)


STREET_TYPES_FR_EN = (("Rue", "Street"), ("Route", "Road"), ("Avenue", "Avenue"), ("Boulevard", "Boulevard"),
                      ("Impasse", "Lane"), ("Ruelle", "Lane"), ("Place", "Square"), ("Autoroute", "Highway"),
                      ("Rond-point", "Roundabout"), ("Carrefour", "Junction"), ("Chemin", "Path"), ("Allée", "Walk"),
                      ("Escalier", "Stairs"), ("Sentier", "Trail"), ("Sortie", "Exit"), ("Passage", "Passage"))
FR_PREPOSITION = r"^(de la |de l'|du |des |de |d'|of the |of )"


# Arabic street-type words typed in Latin letters ("Shari' Bakhistay"); not "Tarek", also a first name.
ARABIZI_TYPES = {"shari": ("Rue", "Street"), "sharia": ("Rue", "Street"), "chareh": ("Rue", "Street"),
                 "tarik": ("Route", "Road"), "tariq": ("Route", "Road")}


def _arabizi_type(name):
    head, _, rest = name.partition(" ")
    return ARABIZI_TYPES.get(strip_accents(head.lower()).strip("'’")), rest.strip()


def fr_to_en_street(name):
    """'Rue des Émigrés' -> 'Émigrés Street', "Route d'Aley" -> 'Aley Road', "Shari' Bakhistay" ->
    'Bakhistay Street'."""
    types, rest = _arabizi_type(name)
    if types and rest and rest.split()[-1].lower() not in {en.lower() for _, en in STREET_TYPES_FR_EN}:
        return f"{rest} {types[1]}"
    for fr, en in STREET_TYPES_FR_EN:
        if name.lower().startswith(fr.lower() + " "):
            rest = re.sub(FR_PREPOSITION, "", name[len(fr) + 1:], flags=re.I)
            main = re.match(r"principale?\b\s*(?:de la |de l'|du |des |de |d')?", rest, flags=re.I)
            if main:   # "Route Principale d'Anjar" -> "Anjar Main Road"
                return f"{rest[main.end():]} Main {en}".strip()
            return fix_en(f"{rest} {en}")
    for fr, en in (("Route", "Road"), ("Rue", "Street")):   # "Anjar Kfarzabad Route" -> "Anjar Kfarzabad Road"
        if name.endswith(" " + fr):
            return f"{name[:-len(fr) - 1]} {en}"
    return name


def en_to_fr_street(name, fr_type=None):
    """'Bonjus Street' -> 'Rue Bonjus', 'Saghbine Main Road' -> 'Route principale Saghbine'; a name
    with no type word takes `fr_type` (from the Arabic name) in front: 'Azra-Mradieh' -> 'Route
    Azra-Mradieh'."""
    low = name.lower()
    for fr in ("Route", "Rue"):   # "Anjar Kfarzabad Route" -> "Route Anjar Kfarzabad"
        if name.endswith(" " + fr):
            return f"{fr} {name[:-len(fr) - 1]}"
    for en, fr in (("main road", "Route principale"), ("main street", "Rue principale"), ("bridge", "Pont")):
        if low.endswith(" " + en) and not (en == "bridge" and " - " in name):   # "Sea Highway - Nahr El Mot Bridge": two names
            return f"{fr} {fr_route_to(name[:-len(en) - 1].strip())}"
    for en, fr in (("private road", "Route privée"),
                   ("residential street", "Rue résidentielle"), ("approach road", "Route d'accès"),
                   ("general road", "Route générale"),
                   ("st.", "Rue"), ("st", "Rue"), ("rd.", "Route"), ("rd", "Route"),
                   *((en.lower(), fr) for fr, en in STREET_TYPES_FR_EN if fr not in ("Impasse",))):
        if low.endswith(" " + en):
            return f"{fr} {name[:-len(en) - 1].strip()}"
    types, rest = _arabizi_type(name)
    if types and rest:
        return f"{types[0]} {rest}"   # "Tarik E'farrin" -> "Route E'farrin"
    return f"{fr_type} {name}" if fr_type and not low.startswith(fr_type.lower() + " ") else name


def english_order(name):
    """OSM English names written the French way round: 'Rue Al Ghomeq' -> 'Al Ghomeq Street',
    'Street Trieste' -> 'Trieste Street'."""
    if not isinstance(name, str):
        return name
    for lead in ("Avenue", "Boulevard"):   # "Avenue Charles Helou" -> "Charles Helou Avenue", not "Avenue des Français"
        rest = name[len(lead) + 1:].strip()
        if name.startswith(lead + " ") and rest and not re.match(FR_PREPOSITION, rest, flags=re.I):
            return f"{rest} {lead}"
    for fr, en in STREET_TYPES_FR_EN:
        if en in ("Avenue", "Boulevard", "Passage"):
            continue
        for lead in (fr, en):
            rest = re.sub(FR_PREPOSITION, "", name[len(lead) + 1:], flags=re.I).strip()
            if name.lower().startswith(lead.lower() + " ") and rest:
                return f"{rest} {en}"
    return name


# The dictionary works both ways: one-word Latin forms of the Arabic entries above.
for _ar, (_fr, _en) in list(AR_WORDS.items()):
    for _w in (_fr, _en):
        _k = strip_accents(_w.lower()) if " " not in _w else None
        if _k and _k not in LATIN_WORDS and not _ar.startswith("ال"):
            LATIN_WORDS[_k] = _ar
LATIN_WORDS.update({"deir": "دير", "ain": "عين", "aayoun": "عيون", "kfar": "كفر", "beit": "بيت", "jabal": "جبل",
                    "jebel": "جبل", "wadi": "وادي", "nahr": "نهر", "haret": "حارة", "hay": "حي", "mazraat": "مزرعة",
                    "dahr": "ضهر", "ras": "راس", "bourj": "برج", "burj": "برج", "tell": "تل", "bir": "بير",
                    "youssef": "يوسف", "yousef": "يوسف", "elie": "الياس", "elias": "الياس", "georges": "جورج",
                    # family names that recur in street names
                    "gemayel": "الجميل", "gemayyel": "الجميل", "chamoun": "شمعون", "khoury": "الخوري",
                    "el-khoury": "الخوري", "helou": "الحلو", "chehab": "شهاب", "solh": "الصلح", "hariri": "الحريري",
                    "karame": "كرامي", "karami": "كرامي", "frangieh": "فرنجية", "jumblatt": "جنبلاط", "salam": "سلام",
                    "sarkis": "سركيس", "lahoud": "لحود", "hrawi": "الهراوي", "aoun": "عون", "berri": "بري",
                    "eddé": "إده", "edde": "إده", "arslan": "أرسلان", "maalouf": "معلوف", "naccache": "نقاش",
                    "tueni": "تويني", "gibran": "جبران", "zouk": "ذوق", "jounieh": "جونية",
                    "lebanon": "لبنان", "liban": "لبنان", "zone": "منطقة", "arz": "الأرز", "beirut": "بيروت",
                    "beyrouth": "بيروت", "damascus": "دمشق", "damas": "دمشق", "international": "الدولي", "tarik": "طريق",
                    "tariq": "طريق", "section": "قسم", "central": "المركزي", "centrale": "المركزية", "mountain": "جبل",
                    "trail": "درب", "pavillon": "جناح", "saida": "صيدا", "sidon": "صيدا", "mont": "جبل", "lake": "بحيرة",
                    "lac": "بحيرة", "view": "إطلالة", "abou": "أبو", "abu": "أبو", "sea": "البحر", "mer": "البحر",
                    "verte": "الخضراء", "vert": "الأخضر", "rouge": "الأحمر", "souq": "سوق", "mufti": "المفتي",
                    "patriarche": "البطريرك", "patriarch": "البطريرك", "sfeir": "صفير", "mohamad": "محمد",
                    "mohammad": "محمد", "mohammed": "محمد", "akram": "أكرم", "farah": "فرح", "kamil": "كامل",
                    "basma": "بسمة", "armenie": "أرمينيا", "armenia": "أرمينيا", "taleet": "طلعة", "talet": "طلعة",
                    "nabi": "النبي", "dhour": "ضهور", "zanket": "زنقة", "haddad": "حداد", "ghosn": "غصن",
                    "makhoul": "مخول", "nasr": "نصر", "salameh": "سلامة", "issa": "عيسى", "mansour": "منصور",
                    "chahine": "شاهين", "younes": "يونس", "hussein": "حسين", "mahmoud": "محمود", "tarek": "طارق",
                    "ziad": "زياد", "jamil": "جميل", "adnan": "عدنان", "abbas": "عباس", "farid": "فريد",
                    "wadih": "وديع", "kassem": "قاسم", "mourad": "مراد", "hayek": "الحايك", "chamoun": "شمعون",
                    "murr": "المر", "fattal": "فتال", "rifai": "الرفاعي", "husseini": "الحسيني", "zein": "الزين",
                    "jean": "جان", "louis": "لويس", "antoun": "أنطون", "dimitri": "ديمتري", "auguste": "أوغست",
                    "kherbet": "خربة", "khirbet": "خربة", "qobbeh": "القبة", "qoubbeh": "القبة", "jdeideh": "الجديدة",
                    "maalaka": "المعلقة", "mazraa": "المزرعة",
                    # honorifics that open many street names
                    "allamah": "العلامة", "allama": "العلامة", "allameh": "العلامة", "sayyed": "السيد",
                    "sayed": "السيد", "sayyid": "السيد", "hajj": "الحاج", "haj": "الحاج", "hadj": "الحاج",
                    "docteur": "الدكتور", "doctor": "الدكتور", "dr": "الدكتور", "professeur": "البروفسور",
                    "professor": "البروفسور", "ustaz": "الأستاذ", "oustaz": "الأستاذ", "moutran": "المطران",
                    "cardinal": "الكاردينال", "frere": "الأخ", "soeur": "الأخت", "sitt": "الست",
                    "naccache": "نقاش", "khoury": "الخوري", "rafii": "الرافعي", "kabbara": "كبارة",
                    "salaheddine": "صلاح الدين", "salahedine": "صلاح الدين", "nasreddine": "نصر الدين",
                    "fakhreddine": "فخر الدين", "fakhredine": "فخر الدين", "badreddine": "بدر الدين",
                    "kamaleddine": "كمال الدين", "alaeddine": "علاء الدين", "chamseddine": "شمس الدين",
                    "charafeddine": "شرف الدين", "zeineddine": "زين الدين", "taqieddine": "تقي الدين",
                    "eddine": "الدين", "abdallah": "عبدالله", "abdullah": "عبدالله", "abdel": "عبد",
                    "abdul": "عبد", "hamra": "الحمرا", "negib": "نجيب", "azouri": "عازوري"})

# Dictionary keyed without letter variants (ى/ي, ة/ه, hamza on alef), so "المستشفي" finds "مستشفى".
AR_WORDS_NORM = {lex_ar_key(k).replace("ة", "ه"): v for k, v in AR_WORDS.items()}


def _theme_vocabulary():
    """The themed street names double as a French/English <-> Arabic vocabulary of nature words:
    "Rue des Pins" in OSM is "شارع الصنوبر", not a letter-by-letter "شارع بينس"."""
    from .themes import THEMES
    for entries in THEMES.values():
        for ar, fr, en in entries:
            noun = re.sub(r"^(des|du|de la|de l'|de)\s*", "", fr)
            for latin in (noun, en):
                for form in {latin, latin.rstrip("s")}:
                    key = strip_accents(form.lower())
                    if " " not in key and key and key not in LATIN_WORDS:
                        LATIN_WORDS[key] = ar
                        THEME_LATIN.add(key)


THEME_LATIN = set()   # nature words from the themes, also given names after a title: "Mère Marguerite Marie"
PERSON_TITLES = {"mere", "soeur", "sœur", "sainte", "saint", "ste", "st", "madame", "mme", "mlle", "mother", "sister",
                 "pere", "frere", "father", "brother", "docteur", "dr", "doctor"}
GIVEN_AR = {"marguerite": "مارغريت", "rose": "روز", "violette": "فيوليت", "lily": "ليلي", "daisy": "ديزي",
            "iris": "إيريس", "jasmine": "جاسمين", "olivier": "أوليفييه", "ruby": "روبي", "amber": "أمبر"}


_theme_vocabulary()
_theme_arabic()
LATIN_WORDS.update({
    # countries and cities that name streets in Beirut and elsewhere
    "france": "فرنسا", "bresil": "البرازيل", "brasil": "البرازيل", "brazil": "البرازيل", "egypte": "مصر",
    "egypt": "مصر", "syrie": "سوريا", "paris": "باريس", "londres": "لندن", "london": "لندن", "rome": "روما",
    "mexique": "المكسيك", "mexico": "المكسيك", "argentine": "الأرجنتين", "argentina": "الأرجنتين",
    "chili": "تشيلي", "venezuela": "فنزويلا", "koweit": "الكويت", "kuwait": "الكويت", "jordanie": "الأردن",
    "jordan": "الأردن", "irak": "العراق", "iraq": "العراق", "palestine": "فلسطين", "jerusalem": "القدس",
    "bagdad": "بغداد", "baghdad": "بغداد", "caire": "القاهرة", "cairo": "القاهرة", "istanbul": "اسطنبول",
    "moscou": "موسكو", "moscow": "موسكو", "washington": "واشنطن", "canada": "كندا", "australie": "أستراليا",
    "australia": "أستراليا", "amerique": "أميركا", "america": "أميركا", "italie": "إيطاليا", "italy": "إيطاليا",
    "espagne": "إسبانيا", "spain": "إسبانيا", "grece": "اليونان", "greece": "اليونان", "chypre": "قبرص",
    "cyprus": "قبرص", "tunisie": "تونس", "tunis": "تونس", "algerie": "الجزائر", "maroc": "المغرب",
    "turquie": "تركيا", "turkey": "تركيا", "beyrouth-damas": "بيروت دمشق", "baalbeck": "بعلبك",
    # common words in Latin-only names
    "gare": "المحطة", "internationale": "الدولية", "jesus": "يسوع", "jami": "الجامع", "jamii": "الجامع",
    "jameh": "الجامع", "avenida": "جادة", "consul": "القنصل", "ambassade": "السفارة", "embassy": "السفارة",
    "universite": "الجامعة", "port": "المرفأ", "aeroport": "المطار", "airport": "المطار", "corniche": "كورنيش",
    "marche": "السوق", "souk": "سوق", "vieux": "القديم", "vieille": "القديمة", "nouveau": "الجديد",
    "nord": "الشمالي", "sud": "الجنوبي", "est": "الشرقي", "ouest": "الغربي", "north": "الشمالي",
    "south": "الجنوبي", "east": "الشرقي", "west": "الغربي", "upper": "العلوي", "lower": "السفلي",
    "pont": "جسر", "bridge": "جسر", "tunnel": "نفق", "plage": "الشاطئ", "beach": "الشاطئ", "foret": "الغابة",
    "forest": "الغابة", "village": "القرية", "colline": "التلة", "hill": "التلة", "valley": "الوادي",
    "vallee": "الوادي", "rivière": "النهر", "riviere": "النهر", "river": "النهر", "fleuve": "النهر",
    "knise": "كنيسة", "knisse": "كنيسة", "kniseh": "كنيسة", "knisseh": "كنيسة",
    # French and English words of Latin-only names, so "Place des Martyrs Assyriens" is "ساحة
    # الشهداء الآشوريين", not the sounds "مارتيرس أسيرينس"
    "martyrs": "الشهداء", "martyr": "الشهيد", "assyriens": "الآشوريين", "assyrian": "الآشوري",
    "assyrians": "الآشوريين", "armeniens": "الأرمن", "armenians": "الأرمن", "independance": "الاستقلال",
    "independence": "الاستقلال", "republique": "الجمهورية", "republic": "الجمهورية", "pavilion": "جناح",
    "pavillion": "جناح", "engineer": "المهندس", "ingenieur": "المهندس", "awqaf": "الأوقاف", "wakfs": "الأوقاف",
    "byblos": "جبيل",
})
EN_TRAILING_TYPES.update({"st", "st.", "rd", "rd.", "ave", "ave."})
# Types that name a whole "A - B Road"; any other ("Bridge", "Entrance") belongs to the last part.
ROAD_TYPES = {"street", "road", "highway", "avenue", "boulevard", "lane", "st", "rd", "ave"}
EN_TRAILING_TYPES.update({"bridge", "entrance", "exit", "tunnel", "roundabout", "junction", "interchange"})
LATIN_WORDS.update({"entrance": "مدخل", "exit": "مخرج", "roundabout": "مستديرة", "junction": "تقاطع",
                    "interchange": "تقاطع", "ferme": "المزرعة", "farm": "المزرعة", "maternelle": "الحضانة"})
AR_WORDS_NORM.update({lex_ar_key(k).replace("ة", "ه"): v for k, v in {
    "أتستراد": ("Autoroute", "Highway"), "اتستراد": ("Autoroute", "Highway"), "أوتوستراد": ("Autoroute", "Highway"),
    "اوتوستراد": ("Autoroute", "Highway"), "نوتردام": ("Notre-Dame", "Notre Dame"), "الشق": ("ech-Chaq", "ash-Shaq"),
    "كورنيش": ("Corniche", "Corniche"), "ساحة": ("Place", "Square"), "حارة": ("Haret", "Haret"),
}.items()})
